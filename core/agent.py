"""
core/agent.py — The FRIDAY agent orchestrator.

This is the brain. It wires together:
    Router → Planner → Skill Matcher → Shell Executor → Memory

Every user input flows through this pipeline.
"""

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.markdown import Markdown

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

import os
import json
import logging

logger = logging.getLogger("friday.agent")
console = Console()


class FridayAgent:
    """
    The core FRIDAY agent.
    
    Pipeline per turn:
        1. Classify intent (router)
        2. Retrieve relevant memory
        3. Check for matching skill
        4. Generate execution plan
        5. Execute plan (skill or shell)
        6. Store results in memory
        7. Return output to user
    """

    def __init__(self):
        self._settings = get_settings()
        self.state = AgentState()
        self.session = SessionMemory()
        self.mempalace = MemPalaceClient()
        self.router = ExecutorRouter()
        self.critic = CriticVerifier()
        self.deterministic_verifier = DeterministicVerifier()
        self.reflection = ReflectionEngine()
        self._skills = load_skills()

        logger.info(
            f"FRIDAY initialized | skills={len(self._skills)} | "
            f"memories={self.mempalace.count} | safe_mode={self.state.safe_mode}"
        )

    def process(self, user_input: str) -> str:
        """
        Process a single user input through the full pipeline.
        
        Args:
            user_input: Raw text from the user.
        
        Returns:
            Response string to display.
        """
        tracer = get_trace()
        tracer.clear()
        tracer.set_input(user_input)
        
        # ── Step 1: Store user input in session memory ────────────────
        self.session.add("user", user_input)
        logger.info(f"Input: {user_input}")

        # ── Step 2: Classify intent ───────────────────────────────────
        intent_info = classify_intent(user_input)
        tracer.set_intent(intent_info)
        intent_name = intent_info.get("intent", "chat")
        logger.info(f"Intent: {intent_name} (confidence: {intent_info.get('confidence', 0):.2f})")

        self._show_intent(intent_info)

        # ── Step 3: Retrieve memory context ───────────────────────────
        session_context = self.session.get_context_string(n=3)
        longterm_context = self.mempalace.recall_context_string(user_input)
        memory_context = ""
        if longterm_context:
            memory_context = f"Long-term: {longterm_context}"
        if session_context:
            memory_context += f"\nSession: {session_context}" if memory_context else f"Session: {session_context}"

        # ── Step 4: Handle by intent type ─────────────────────────────

        if intent_name == "chat":
            response = self._handle_chat(user_input, memory_context)

        elif intent_name == "memory_query":
            response = self._handle_memory_query(user_input)

        elif intent_name in ("shell_task", "skill_task"):
            response = self._handle_task(user_input, intent_info, memory_context)

        else:
            response = self._handle_chat(user_input, memory_context)

        # ── Step 5: Store response in memory ──────────────────────────
        # Inject commands run into metadata for reflection
        meta = {"commands_executed": getattr(self, "_temp_commands_run", [])}
        self.session.add("assistant", response, intent=intent_name, metadata=meta)
        self.state.record_command(user_input)
        
        # Reset local tracker
        self._temp_commands_run = []

        # ── Step 6: Post-Process Reflection ───────────────────────────
        if intent_info["intent"] in ("shell_task", "skill_task"):
            self.reflection.analyze_turn(self.session)
            # Re-sync skills in case generator minted one
            self.reload_skills()

        tracer.commit()
        logger.info(f"Response: {response[:200]}")
        return response

    def _handle_chat(self, user_input: str, memory_context: str) -> str:
        """Handle conversational chat intent."""
        response = generate_chat_response(user_input, memory_context)
        console.print()
        console.print(Markdown(response))
        console.print()
        return response

    def _handle_memory_query(self, user_input: str) -> str:
        """Handle memory recall queries."""
        # Search both session and long-term memory
        session_results = self.session.search(user_input)
        longterm_results = self.mempalace.recall(user_input)

        parts = []

        if longterm_results:
            parts.append("[bold cyan]Long-term memories:[/bold cyan]")
            for mem in longterm_results:
                parts.append(f"  [{mem['type']}] {mem['content']}")

        if session_results:
            parts.append("[bold cyan]Session memories:[/bold cyan]")
            for entry in session_results:
                parts.append(f"  [{entry.role}] {entry.content[:150]}")

        if not parts:
            parts.append("[dim]No relevant memories found.[/dim]")

        output = "\n".join(parts)
        console.print()
        console.print(Panel(output, title="🧠 Memory Recall", border_style="cyan"))
        console.print()
        return output

    def _handle_task(self, user_input: str, intent: dict, memory_context: str) -> str:
        """Handle shell_task and skill_task intents."""

        # ── Step A: Try skill match first (ALWAYS) ────────────────────
        matched_skill = match_skill(user_input, self._skills)

        if matched_skill:
            logger.info(f"Skill matched: {matched_skill.name}")
            console.print(f"  [bold green]⚡ Skill matched:[/bold green] {matched_skill.name}")
            console.print(f"  [dim]{matched_skill.description}[/dim]")

            if matched_skill.has_runner:
                result = execute_skill(matched_skill)
                output = self._format_execution_result(result)

                # Store successful outcomes in long-term memory
                if result["executed"] and result["exit_code"] == 0:
                    self.mempalace.store(
                        f"Ran skill '{matched_skill.name}' for: {user_input[:100]}",
                        memory_type="outcome",
                        tags=[matched_skill.name],
                    )

                response = generate_task_response(user_input, f"Executed skill: {matched_skill.name}", output, memory_context)
                console.print()
                console.print(Markdown(response))
                console.print()
                return response
            else:
                console.print(f"  [yellow]Skill '{matched_skill.name}' has no runner (run.sh)[/yellow]")

        # ── Step B: Generate plan via LLM ─────────────────────────────
        plan = create_plan(user_input, intent, memory_context)
        get_trace().set_plan(plan)
        logger.info(f"Plan: type={plan['type']}, steps={len(plan.get('steps', []))}")

        self._show_plan(plan)

        # ── Step C: Execute plan ──────────────────────────────────────
        if plan["type"] == "chat":
            return self._handle_chat(user_input, memory_context)

        if plan["type"] == "shell" or plan.get("requires_shell"):
            shell_output = self._execute_shell_plan(plan, user_input)
            plan_str = json.dumps(plan, indent=2)
            response = generate_task_response(user_input, f"Executed shell plan:\n{plan_str}", shell_output, memory_context)
            console.print()
            console.print(Markdown(response))
            console.print()
            return response

        # Fallback to chat
        return self._handle_chat(user_input, memory_context)

    def _execute_shell_plan(self, plan: dict, user_input: str) -> str:
        """Execute shell commands from a plan."""
        outputs = []
        if not hasattr(self, "_temp_commands_run"):
            self._temp_commands_run = []

        for step in plan.get("steps", []):
            command_obj = step.get("command")
            if not command_obj:
                continue

            # Generate a printable representation of the command
            if isinstance(command_obj, dict):
                cmd_repr = json.dumps(command_obj)
            else:
                cmd_repr = str(command_obj)
                
            console.print(f"  [bold]$[/bold] [cyan]{cmd_repr}[/cyan]")
            self._temp_commands_run.append(cmd_repr)

            # Route through the Executor Router
            if isinstance(command_obj, dict):
                result = self.router.execute(command_obj, default_cwd=os.getcwd())
            else:
                # Fallback if planner hallucinates raw string
                result = self.router.shell.execute(str(command_obj))
                
            get_trace().add_execution(result)
            output = self._format_execution_result(result)
            outputs.append(output)
            
            # Phase 11: Fast Deterministic Verification
            det_eval = {"success": False, "confidence": 0.0, "reason": ""}
            if isinstance(command_obj, dict):
                det_eval = self.deterministic_verifier.verify(command_obj, result, default_cwd=os.getcwd())
                
            evaluation = None
            if det_eval["confidence"] >= 0.9:
                console.print(f"  [dim]Deterministic Verifier (conf:{det_eval['confidence']}):[/dim] ✓" if det_eval["success"] else f"  [dim]Deterministic Verifier:[/dim] ✗")
                evaluation = {
                    "status": "success" if det_eval["success"] else "failure",
                    "retry_recommended": not det_eval["success"],
                    "feedback": det_eval["reason"]
                }
            else:
                # Post-execution LLM Critic Verification Fallback
                evaluation = self.critic.verify(user_input, cmd_repr, result)
            
            get_trace().add_evaluation(evaluation)
            if evaluation["status"] == "failure":
                console.print(f"  [yellow]Verifier Flagged Issue:[/yellow] {evaluation['feedback']}")
                if evaluation["retry_recommended"]:
                    console.print("  [dim]Retry recommended. (Not strictly re-planning yet to prevent loops)[/dim]")
            else:
                console.print(f"  [green]Verified:[/green] {evaluation.get('feedback', 'Success.')}\n")

            # Store successful outcomes
            if result["executed"] and result["exit_code"] == 0:
                self.mempalace.store(
                    f"Executed: {cmd_repr} | Result: {result['stdout'][:150]}",
                    memory_type="outcome",
                    tags=["shell"],
                )

            # Stop on failure
            if result.get("exit_code", -1) != 0 and result.get("executed"):
                console.print("[red]  Step failed. Stopping plan execution.[/red]")
                break

        return "\n".join(outputs) if outputs else "[No commands to execute]"

    def _format_execution_result(self, result: dict) -> str:
        """Format a shell/skill execution result for display."""
        parts = []

        if result.get("stdout"):
            stdout = result["stdout"].strip()
            if stdout:
                console.print(Panel(stdout, border_style="green", title="output"))
                parts.append(stdout)

        if result.get("stderr"):
            stderr = result["stderr"].strip()
            if stderr:
                console.print(Panel(stderr, border_style="red", title="stderr"))
                parts.append(f"[stderr] {stderr}")

        if not result.get("executed"):
            msg = result.get("stderr", "Command was not executed.")
            if not parts:
                console.print(f"  [dim]{msg}[/dim]")
                parts.append(msg)

        exit_code = result.get("exit_code", -1)
        if result.get("executed"):
            color = "green" if exit_code == 0 else "red"
            console.print(f"  [dim]exit code: [{color}]{exit_code}[/{color}][/dim]")

        return "\n".join(parts)

    def _show_intent(self, intent: dict):
        """Display classified intent."""
        conf = intent["confidence"]
        intent_name = intent["intent"]

        color_map = {
            "chat": "blue",
            "shell_task": "yellow",
            "skill_task": "green",
            "memory_query": "cyan",
        }
        color = color_map.get(intent_name, "white")

        bar_len = int(conf * 20)
        bar = "█" * bar_len + "░" * (20 - bar_len)

        console.print(
            f"  [dim]intent:[/dim] [{color}]{intent_name}[/{color}] "
            f"[dim]{bar} {conf:.0%}[/dim]"
        )

    def _show_plan(self, plan: dict):
        """Display the execution plan."""
        if not plan.get("steps"):
            return

        console.print(f"  [dim]plan:[/dim] [bold]{plan['type']}[/bold]", end="")
        if plan.get("reasoning"):
            console.print(f" [dim]— {plan['reasoning'][:80]}[/dim]")
        else:
            console.print()

        for i, step in enumerate(plan.get("steps", []), 1):
            action = step.get("action", "")
            cmd = step.get("command", "")
            skill = step.get("skill", "")

            console.print(f"  [dim]{i}.[/dim] {action}", end="")
            if cmd:
                console.print(f" [cyan]→ {cmd}[/cyan]", end="")
            if skill:
                console.print(f" [green]⚡ {skill}[/green]", end="")
            console.print()

    def reload_skills(self):
        """Reload skills from disk."""
        self._skills = load_skills()
        logger.info(f"Skills reloaded: {len(self._skills)} found")
        return len(self._skills)
