"""
core/agent.py — Friday agent orchestrator.

Router → Planner → Skills → Shell (with bounded retries) → Memory
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from rich.markdown import Markdown
from rich.panel import Panel

from core.router import classify_intent
from core.planner import create_plan, generate_chat_response, generate_task_response
from core.state import AgentState
from memory.session import SessionMemory
from memory.mempalace_client import MemPalaceClient
from skills.loader import load_skills
from skills.matcher import match_skill
from skills.executor import execute_skill
from core.executor_router import ExecutorRouter
from core.critic import CriticVerifier
from core.verifier import DeterministicVerifier
from core.reflection import ReflectionEngine
from core.trace import get_trace
from config.settings import get_settings
from core.persona import read_persona_bundle
from core.ui import console

logger = logging.getLogger("friday.agent")

_MAX_SHELL_ATTEMPTS = 3


class FridayAgent:
    """Core Friday agent."""

    def __init__(self, verbose: bool = False):
        self._settings = get_settings()
        self.verbose = bool(verbose) or os.environ.get("FRIDAY_VERBOSE", "").lower() in (
            "1",
            "true",
            "yes",
        )
        self.state = AgentState()
        self.session = SessionMemory()
        self.mempalace = MemPalaceClient()
        self.router = ExecutorRouter()
        self.critic = CriticVerifier()
        self.deterministic_verifier = DeterministicVerifier()
        self.reflection = ReflectionEngine()
        self._skills = load_skills()

        logger.info(
            "Friday initialized | skills=%s | memories=%s | safe_mode=%s | verbose=%s",
            len(self._skills),
            self.mempalace.count,
            self.state.safe_mode,
            self.verbose,
        )

    def process(self, user_input: str) -> str:
        tracer = get_trace()
        tracer.clear()
        tracer.set_input(user_input)

        self.session.add("user", user_input)
        logger.info("Input: %s", user_input)

        intent_info = classify_intent(user_input)
        tracer.set_intent(intent_info)
        intent_name = intent_info.get("intent", "chat")
        cognitive_load = intent_info.get("cognitive_load", "medium")
        if cognitive_load not in ("low", "medium", "high"):
            cognitive_load = "medium"

        logger.info(
            "Intent: %s confidence=%s cognitive_load=%s",
            intent_name,
            intent_info.get("confidence", 0),
            cognitive_load,
        )

        if self.verbose:
            self._show_intent(intent_info)

        persona_bundle = read_persona_bundle()

        session_context = self.session.get_context_string(n=3)
        longterm_context = self.mempalace.recall_context_string(user_input)
        memory_context = ""
        if longterm_context:
            memory_context = f"Long-term: {longterm_context}"
        if session_context:
            memory_context += (
                f"\nSession: {session_context}" if memory_context else f"Session: {session_context}"
            )

        if intent_name == "chat":
            response = self._handle_chat(user_input, memory_context, cognitive_load, persona_bundle)
        elif intent_name == "memory_query":
            response = self._handle_memory_query(user_input)
        elif intent_name in ("shell_task", "skill_task"):
            response = self._handle_task(
                user_input, intent_info, memory_context, cognitive_load, persona_bundle
            )
        else:
            response = self._handle_chat(user_input, memory_context, cognitive_load, persona_bundle)

        meta = {"commands_executed": getattr(self, "_temp_commands_run", [])}
        self.session.add("assistant", response, intent=intent_name, metadata=meta)
        self.state.record_command(user_input)
        self._temp_commands_run = []

        if intent_info["intent"] in ("shell_task", "skill_task"):
            self.reflection.analyze_turn(self.session)
            self.reload_skills()

        tracer.commit()
        logger.info("Response: %s", response[:200])
        return response

    def _handle_chat(
        self,
        user_input: str,
        memory_context: str,
        cognitive_load: str,
        persona_bundle: str,
    ) -> str:
        response = generate_chat_response(
            user_input, memory_context, cognitive_load, persona_context=persona_bundle
        )
        console.print()
        console.print(Markdown(response))
        console.print()
        return response

    def _handle_memory_query(self, user_input: str) -> str:
        session_results = self.session.search(user_input)
        longterm_results = self.mempalace.recall(user_input)
        parts: list[str] = []

        if longterm_results:
            parts.append("[friday.accent]Long-term[/friday.accent]")
            for mem in longterm_results:
                parts.append(f"  · [{mem['type']}] {mem['content']}")

        if session_results:
            parts.append("[friday.accent]This session[/friday.accent]")
            for entry in session_results:
                parts.append(f"  · [{entry.role}] {entry.content[:150]}")

        if not parts:
            parts.append("[friday.dim]Nothing matched that recall.[/friday.dim]")

        output = "\n".join(parts)
        console.print()
        console.print(Panel(output, title="Memory", border_style="friday.accent", padding=(0, 1)))
        console.print()
        return output

    def _handle_task(
        self,
        user_input: str,
        intent: dict,
        memory_context: str,
        cognitive_load: str,
        persona_bundle: str,
    ) -> str:
        matched_skill = match_skill(user_input, self._skills)

        if matched_skill:
            logger.info("Skill matched: %s", matched_skill.name)
            if self.verbose:
                console.print(f"  [friday.ok]Skill:[/friday.ok] {matched_skill.name}")
                console.print(f"  [friday.dim]{matched_skill.description}[/friday.dim]")
            elif not self.verbose:
                console.print("[friday.dim]…[/friday.dim]")

            if matched_skill.has_runner:
                result = execute_skill(matched_skill)
                output = self._format_execution_result(result, quiet=not self.verbose)

                if result["executed"] and result["exit_code"] == 0:
                    self.mempalace.store(
                        f"Ran skill '{matched_skill.name}' for: {user_input[:100]}",
                        memory_type="outcome",
                        tags=[matched_skill.name],
                    )

                response = generate_task_response(
                    user_input,
                    f"Ran the “{matched_skill.name}” skill you already had.",
                    output,
                    memory_context,
                    cognitive_load,
                    persona_context=persona_bundle,
                )
                console.print()
                console.print(Markdown(response))
                console.print()
                return response
            if self.verbose:
                console.print(f"  [friday.warn]Skill '{matched_skill.name}' has no runner.[/friday.warn]")

        return self._autonomous_shell_loop(
            user_input, intent, memory_context, cognitive_load, persona_bundle
        )

    def _autonomous_shell_loop(
        self,
        user_input: str,
        intent: dict,
        memory_context: str,
        cognitive_load: str,
        persona_bundle: str,
    ) -> str:
        if not self.verbose:
            console.print("[friday.dim]…[/friday.dim]")

        feedback = ""
        last_combined = ""
        plan_cog = cognitive_load
        seen_plans: set[str] = set()
        attempt = 0

        while attempt < _MAX_SHELL_ATTEMPTS:
            attempt += 1
            alternate = attempt >= _MAX_SHELL_ATTEMPTS
            if attempt >= 2:
                plan_cog = "high"

            plan = create_plan(
                user_input,
                intent,
                memory_context,
                plan_cog,
                retry_context=feedback,
                attempt=attempt,
                alternate_strategy=alternate,
                persona_context=persona_bundle,
            )
            get_trace().set_plan(plan)
            logger.info("Plan attempt %s type=%s steps=%s", attempt, plan["type"], len(plan.get("steps", [])))

            if self.verbose:
                self._show_plan(plan)

            sig = self._plan_signature(plan)
            if sig in seen_plans:
                feedback = (
                    "That exact command sequence was already tried. "
                    "Use a different tool, path, or order (no repeated pkill/killall)."
                )
                continue
            seen_plans.add(sig)

            if plan["type"] == "chat":
                if intent.get("intent") in ("shell_task", "skill_task") and attempt < _MAX_SHELL_ATTEMPTS:
                    feedback = "User needed actionable shell output; avoid pure chat."
                    continue
                return self._handle_chat(user_input, memory_context, plan_cog, persona_bundle)

            if plan["type"] != "shell" and not plan.get("requires_shell"):
                feedback = "Emit a concrete shell plan with argv-style commands."
                continue

            ok, combined, fb = self._execute_shell_plan(
                plan, user_input, plan_cog, quiet=not self.verbose
            )
            last_combined = combined
            if ok:
                summary = self._friendly_plan_summary(plan)
                response = generate_task_response(
                    user_input,
                    summary,
                    combined,
                    memory_context,
                    plan_cog,
                    persona_context=persona_bundle,
                )
                console.print()
                console.print(Markdown(response))
                console.print()
                return response

            if "cancelled" in (combined or "").lower() or "cancelled" in (fb or "").lower():
                feedback = (
                    "The run was cancelled or blocked. Do not loop the same command; "
                    "either ask how the user wants to proceed or use a different approach."
                )
            else:
                feedback = fb or combined or "Unknown failure; try a different command sequence."

        response = generate_task_response(
            user_input,
            "I could not finish that after a few different approaches—want to try narrower steps?",
            last_combined,
            memory_context,
            "high",
            persona_context=persona_bundle,
        )
        console.print()
        console.print(Markdown(response))
        console.print()
        return response

    def _plan_signature(self, plan: dict) -> str:
        parts: list[str] = []
        for s in plan.get("steps") or []:
            c = s.get("command")
            if c is not None:
                parts.append(json.dumps(c, sort_keys=True) if isinstance(c, dict) else str(c))
        if parts:
            return "|".join(parts)
        return json.dumps(plan, sort_keys=True, default=str)[:800]

    def _friendly_plan_summary(self, plan: dict) -> str:
        steps = plan.get("steps") or []
        bits: list[str] = []
        for s in steps[:5]:
            a = (s.get("action") or "").strip()
            if a:
                bits.append(a)
        if not bits:
            return "Ran the steps we planned on your machine."
        return "Here is what I did: " + " · ".join(bits)

    def _execute_shell_plan(
        self,
        plan: dict,
        user_input: str,
        cognitive_load: str,
        *,
        quiet: bool,
    ) -> tuple[bool, str, str]:
        outputs: list[str] = []
        if not hasattr(self, "_temp_commands_run"):
            self._temp_commands_run = []

        failure_feedback = ""

        for step in plan.get("steps", []):
            command_obj = step.get("command")
            if not command_obj:
                continue

            if isinstance(command_obj, dict):
                cmd_repr = json.dumps(command_obj)
            else:
                cmd_repr = str(command_obj)

            if self.verbose:
                console.print(f"  [bold]$[/bold] [friday.info]{cmd_repr}[/friday.info]")
            self._temp_commands_run.append(cmd_repr)

            if isinstance(command_obj, dict):
                result = self.router.execute(command_obj, default_cwd=os.getcwd())
            else:
                result = self.router.shell.execute(str(command_obj))

            get_trace().add_execution(result)
            output = self._format_execution_result(result, quiet=quiet)
            outputs.append(output)

            det_eval: dict[str, Any] = {"success": False, "confidence": 0.0, "reason": ""}
            if isinstance(command_obj, dict):
                det_eval = self.deterministic_verifier.verify(
                    command_obj, result, default_cwd=os.getcwd()
                )

            if det_eval["confidence"] >= 0.9:
                evaluation = {
                    "status": "success" if det_eval["success"] else "failure",
                    "retry_recommended": not det_eval["success"],
                    "feedback": det_eval["reason"],
                }
            else:
                evaluation = self.critic.verify(user_input, cmd_repr, result, cognitive_load)

            get_trace().add_evaluation(evaluation)

            if self.verbose:
                if evaluation["status"] == "failure":
                    console.print(f"  [friday.warn]Check:[/friday.warn] {evaluation['feedback']}")
                else:
                    console.print(f"  [friday.ok]Looks good —[/friday.ok] {evaluation.get('feedback', '')}")

            exit_code = result.get("exit_code", -1)
            executed = result.get("executed")

            if executed and exit_code != 0:
                failure_feedback = result.get("stderr") or f"exit {exit_code}"
                return False, "\n".join(outputs), failure_feedback

            if evaluation["status"] == "failure":
                failure_feedback = evaluation.get("feedback") or "Verifier flagged this step."
                return False, "\n".join(outputs), failure_feedback

            if executed and exit_code == 0:
                self.mempalace.store(
                    f"Executed: {cmd_repr} | Result: {result['stdout'][:150]}",
                    memory_type="outcome",
                    tags=["shell"],
                )

        text = "\n".join(outputs) if outputs else "[No commands to execute]"
        if not outputs:
            return False, text, "Planner produced no runnable commands."
        return True, text, ""

    def _format_execution_result(self, result: dict, *, quiet: bool) -> str:
        parts: list[str] = []

        if result.get("stdout"):
            stdout = result["stdout"].strip()
            if stdout:
                if not quiet:
                    console.print(Panel(stdout, border_style="friday.ok", title="output"))
                parts.append(stdout)

        if result.get("stderr"):
            stderr = result["stderr"].strip()
            if stderr:
                if not quiet:
                    console.print(Panel(stderr, border_style="friday.err", title="stderr"))
                parts.append(f"[stderr] {stderr}")

        if not result.get("executed"):
            msg = result.get("stderr", "Command was not executed.")
            if not quiet and not parts:
                console.print(f"  [friday.dim]{msg}[/friday.dim]")
            if not parts:
                parts.append(msg)

        exit_code = result.get("exit_code", -1)
        if result.get("executed") and not quiet:
            color = "friday.ok" if exit_code == 0 else "friday.err"
            console.print(f"  [friday.dim]exit[/friday.dim] [{color}]{exit_code}[/{color}]")

        return "\n".join(parts)

    def _show_intent(self, intent: dict) -> None:
        conf = intent["confidence"]
        intent_name = intent["intent"]
        color_map = {
            "chat": "friday.info",
            "shell_task": "friday.warn",
            "skill_task": "friday.ok",
            "memory_query": "friday.accent",
        }
        color = color_map.get(intent_name, "white")
        bar_len = int(conf * 20)
        bar = "█" * bar_len + "░" * (20 - bar_len)
        cl = intent.get("cognitive_load", "medium")
        console.print(
            f"  [friday.dim]intent[/friday.dim] [{color}]{intent_name}[/{color}] "
            f"[friday.dim]{bar} {conf:.0%}  load {cl}[/friday.dim]"
        )

    def _show_plan(self, plan: dict) -> None:
        if not plan.get("steps"):
            return
        console.print(f"  [friday.dim]plan[/friday.dim] [bold]{plan['type']}[/bold]", end="")
        if plan.get("reasoning"):
            console.print(f" [friday.dim]— {plan['reasoning'][:100]}[/friday.dim]")
        else:
            console.print()
        for i, step in enumerate(plan.get("steps", []), 1):
            action = step.get("action", "")
            cmd = step.get("command", "")
            skill = step.get("skill", "")
            console.print(f"  [friday.dim]{i}.[/friday.dim] {action}", end="")
            if cmd:
                console.print(f" [friday.info]→ {cmd}[/friday.info]", end="")
            if skill:
                console.print(f" [friday.ok]⚡ {skill}[/friday.ok]", end="")
            console.print()

    def reload_skills(self) -> int:
        self._skills = load_skills()
        logger.info("Skills reloaded: %s", len(self._skills))
        return len(self._skills)
