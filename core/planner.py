"""
core/planner.py — Converts classified intent into an execution plan.

Takes user query + intent and produces a structured plan:
  - type: chat | skill | shell
  - steps: ordered list of actions
  - requires_shell: whether shell access is needed

Model tier is chosen from the Groq catalog + per-turn cognitive_load (router).
Always prefers skills over raw shell commands.
"""

import json
from groq import Groq
from config.settings import get_settings
from core.groq_compat import chat_completion_create

PLANNER_SYSTEM_PROMPT = """You are the planning engine for Friday, a local CLI copilot.

Given a user query and its classified intent, produce an execution plan.

Rules:
1. ALWAYS prefer using a skill if one could handle the task.
2. For shell steps you MUST output STRUCTURED command objects (type + action + params). Never rely on raw shell strings.
3. Keep plans SHORT — 1 to 3 steps maximum.
4. If the user asks for factual information (time, disk space, files), emit a "shell" plan, even when intent was "chat".
5. Only emit type "chat" for greetings, opinions, or chat with no machine facts required.
6. Never suggest destructive commands (rm -rf /, sudo rm, disk writes to system paths).
7. Persona self-updates: to change long-lived preferences, you may add a step with
   {"type":"persona","action":"write"|"append","params":{"file":"SOUL.md"|"USER.md"|"AGENT.md"|"HEARTBEAT.md","content":"..."}}.
   Only those four filenames. No secrets or API keys.
8. NEVER run interactive terminal programs (nano, vim, vi, less, emacs). Use filesystem read_file / create_file or printf/sed instead.
9. NEVER wrap commands in `bash -c` / `bash -lc` / `sh -c`. Use argv-style system commands only (e.g. find, rg, cat).
10. To locate files by name, use `find` with structured args (e.g. find, HOME path, -name, pattern). Do not invent container or MCP tools.
11. If a previous API or tool error mentioned "tool" or "invalid_request", switch to plain argv shell only—no pseudo tools.

Respond with ONLY valid JSON:
{
  "type": "chat" | "skill" | "shell",
  "steps": [
    {
      "action": "description of step",
      "skill": "skill name if applicable or null",
      "command": {
         "type": "filesystem" | "git" | "system" | "package" | "shell" | "persona",
         "action": "verb or binary name",
         "params": {
             "path": "relative to cwd if filesystem",
             "args": ["argv", "tokens", "only", "no", "shell", "metacharacters"],
             "content": "text if creating a file",
             "file": "one of SOUL.md USER.md AGENT.md HEARTBEAT.md for persona",
             "append": false
         }
      }
    }
  ],
  "requires_shell": true | false,
  "reasoning": "brief private note (not shown to user verbatim)"
}"""


def create_plan(
    user_query: str,
    intent: dict,
    memory_context: str = "",
    cognitive_load: str = "medium",
    *,
    retry_context: str = "",
    attempt: int = 1,
    alternate_strategy: bool = False,
    persona_context: str = "",
) -> dict:
    """
    Generate an execution plan from user query and classified intent.
    
    Args:
        user_query: Original user input.
        intent: Output from router — {"intent": "...", "confidence": ...}
        memory_context: Optional relevant memory to inform planning.
    
    Returns:
        dict with type, steps, requires_shell, and reasoning.
    """
    settings = get_settings()
    client = Groq(api_key=settings.groq_api_key)

    from core.context import EnvironmentContext

    # Build the user message with context
    context_parts = [f"User query: {user_query}"]
    context_parts.append(
        f"Classified intent: {intent['intent']} (confidence: {intent['confidence']}, "
        f"cognitive_load: {cognitive_load})"
    )
    
    env_info = EnvironmentContext.get_info()
    context_parts.append(f"Environment:\n{env_info}")
    
    if memory_context:
        context_parts.append(f"Relevant memory: {memory_context}")

    if persona_context.strip():
        context_parts.append("Persona / self-docs (may inform tone or constraints):\n" + persona_context.strip())

    if retry_context.strip():
        context_parts.append(f"Previous attempt #{attempt - 1} issues (fix these):\n{retry_context.strip()}")

    if attempt > 1:
        context_parts.append(f"This is planning attempt #{attempt}. Adjust commands based on the feedback above.")

    if alternate_strategy:
        context_parts.append(
            "FINAL ATTEMPT: propose a substantially different approach (different tools, order, or assumptions)."
        )

    user_message = "\n".join(context_parts)

    try:
        pm = settings.get_model("plan", cognitive_load)

        def _plan_kwargs(mid: str):
            return {
                "messages": [
                    {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                "temperature": 0.2,
                "max_completion_tokens": 500,
                "response_format": {"type": "json_object"},
            }

        response = chat_completion_create(client, primary_model=pm, builder=_plan_kwargs)

        from core.budget import get_tracker
        get_tracker().record_usage(response.usage)

        raw = response.choices[0].message.content.strip()
        plan = json.loads(raw)

        # Validate and set defaults
        if "type" not in plan:
            plan["type"] = "chat"
        if "steps" not in plan or not isinstance(plan["steps"], list):
            plan["steps"] = []
        if "requires_shell" not in plan:
            plan["requires_shell"] = False
        if "reasoning" not in plan:
            plan["reasoning"] = ""

        return plan

    except Exception as e:
        return {
            "type": "chat",
            "steps": [{"action": f"Error creating plan: {e}", "command": None, "skill": None}],
            "requires_shell": False,
            "reasoning": f"Planning failed: {e}",
        }


def generate_chat_response(
    user_query: str,
    memory_context: str = "",
    cognitive_load: str = "medium",
    persona_context: str = "",
) -> str:
    """
    Generate a conversational response for chat-type intents.
    
    Args:
        user_query: The user's message.
        memory_context: Optional context from memory.
    
    Returns:
        String response to display to the user.
    """
    settings = get_settings()
    client = Groq(api_key=settings.groq_api_key)

    system_msg = (
        "You are Friday — a warm, capable CLI copilot with a feminine voice: direct, kind, "
        "never condescending. You are not a lecturer: skip jargon, acronyms, and implementation "
        "details unless the user explicitly wants depth. "
        "When \"Environment Status\" lists machine-local facts (time, OS, cwd), treat them as "
        "truth for this session. Never invent terminal output. If a fact is missing, offer to "
        "check via shell in plain language."
    )

    messages = [{"role": "system", "content": system_msg}]

    if persona_context.strip():
        messages.append({"role": "system", "content": "Persona files:\n" + persona_context.strip()})
    
    if memory_context:
        messages.append({
            "role": "system",
            "content": f"Relevant context from memory: {memory_context}"
        })
        
    from core.context import EnvironmentContext
    env_info = EnvironmentContext.get_info()
    messages.append({
        "role": "system",
        "content": f"Environment Status:\n{env_info}"
    })
    
    messages.append({"role": "user", "content": user_query})

    try:
        pm = settings.get_model("chat", cognitive_load)

        def _chat_kwargs(mid: str):
            return {
                "messages": messages,
                "temperature": 0.7,
                "max_completion_tokens": 1024,
            }

        response = chat_completion_create(client, primary_model=pm, builder=_chat_kwargs)

        from core.budget import get_tracker
        get_tracker().record_usage(response.usage)

        return response.choices[0].message.content.strip()

    except Exception as e:
        return (
            "I hit a brief glitch talking to the model, so here is the short version: "
            "ask again in a moment, or turn off anything that forces special model tools. "
            f"(detail: {e})"
        )


def generate_task_response(
    user_query: str,
    task_context: str,
    execution_logs: str,
    memory_context: str = "",
    cognitive_load: str = "medium",
    persona_context: str = "",
) -> str:
    """
    Generate a conversational response after executing a task (shell or skill).
    
    Args:
        user_query: The user's original message.
        task_context: A description of the plan or skill that was executed.
        execution_logs: The output and results of the execution.
        memory_context: Optional context from memory.
    
    Returns:
        String response interpreting the results.
    """
    settings = get_settings()
    client = Groq(api_key=settings.groq_api_key)

    system_msg = (
        "You are Friday — same voice as in chat: warm, concise, human. You already ran something "
        "for the user. Explain the outcome in everyday language: what changed, what they can do next. "
        "Do not paste JSON, command objects, stack traces, or log dumps. If something failed, "
        "say what it means in plain words and the gentlest next step—no panic tone."
    )

    messages = [{"role": "system", "content": system_msg}]

    if persona_context.strip():
        messages.append({"role": "system", "content": "Persona files:\n" + persona_context.strip()})
    
    if memory_context:
        messages.append({
            "role": "system",
            "content": f"Relevant context from memory: {memory_context}"
        })

    from core.context import EnvironmentContext
    env_info = EnvironmentContext.get_info()
    messages.append({
        "role": "system",
        "content": f"Environment Status:\n{env_info}"
    })
    
    prompt = (
        f"User query: {user_query}\n"
        f"Task context: {task_context}\n"
        f"Execution logs:\n{execution_logs}\n\n"
        "Please provide your response to the user."
    )
    
    messages.append({"role": "user", "content": prompt})

    try:
        pm = settings.get_model("chat", cognitive_load)

        def _task_chat_kwargs(mid: str):
            return {
                "messages": messages,
                "temperature": 0.5,
                "max_completion_tokens": 1024,
            }

        response = chat_completion_create(client, primary_model=pm, builder=_task_chat_kwargs)

        from core.budget import get_tracker
        get_tracker().record_usage(response.usage)

        return response.choices[0].message.content.strip()

    except Exception as e:
        return (
            "I could not polish the answer through the model just now, but the run already finished—"
            f"check the output above if shown. ({e})"
        )
