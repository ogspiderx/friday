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

PLANNER_SYSTEM_PROMPT = """You are the planning engine for FRIDAY, a CLI AI agent.

Given a user query and its classified intent, produce an execution plan.

Rules:
1. ALWAYS prefer using a skill if one could handle the task.
2. If using the shell, you MUST output a STRUCTURED command object, NOT a raw shell string.
3. Keep plans SHORT — 1 to 3 steps maximum.
4. If the user asks for factual information (time, disk space, files), generate a "shell" plan to find the answer, EVEN IF the intent was classified as "chat". 
5. Only output a "chat" plan for casual conversation, greetings, or opinions where no system information is required.
6. NEVER suggest dangerous commands (rm -rf /, sudo rm, etc.) without flagging them.

Respond with ONLY valid JSON:
{
  "type": "chat" | "skill" | "shell",
  "steps": [
    {
      "action": "description of step", 
      "skill": "skill name if applicable or null",
      "command": {
         "type": "filesystem" | "git" | "system" | "package" | "shell",
         "action": "action_name_or_base_binary",
         "params": { 
             "path": "target path if filesystem", 
             "args": ["flags", "and", "arguments", "if system/git"],
             "content": "file content if creating file"
         }
      }
    }
  ],
  "requires_shell": true | false,
  "reasoning": "brief explanation of your plan"
}"""


def create_plan(
    user_query: str,
    intent: dict,
    memory_context: str = "",
    cognitive_load: str = "medium",
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

    user_message = "\n".join(context_parts)

    try:
        response = client.chat.completions.create(
            model=settings.get_model("plan", cognitive_load),
            messages=[
                {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0.2,
            max_completion_tokens=500,
            response_format={"type": "json_object"},
        )
        
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
        "You are FRIDAY, a sharp, capable AI assistant running as a local CLI agent. "
        "You are helpful, concise, and slightly witty. You have access to the user's "
        "shell and filesystem. Keep responses brief and actionable unless the user "
        "wants a longer conversation. "
        "When \"Environment Status\" includes machine-local facts (current time, OS, cwd), "
        "treat that block as authoritative for this session. Never fabricate terminal output "
        "or pretend a command ran unless it appears in the conversation. If the user needs "
        "a fact that is not in Environment Status, say you can run a shell command to fetch it."
    )

    messages = [{"role": "system", "content": system_msg}]
    
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
        response = client.chat.completions.create(
            model=settings.get_model("chat", cognitive_load),
            messages=messages,
            temperature=0.7,
            max_completion_tokens=1024,
        )
        
        from core.budget import get_tracker
        get_tracker().record_usage(response.usage)
        
        return response.choices[0].message.content.strip()

    except Exception as e:
        return f"[error] Failed to generate response: {e}"


def generate_task_response(
    user_query: str,
    task_context: str,
    execution_logs: str,
    memory_context: str = "",
    cognitive_load: str = "medium",
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
        "You are FRIDAY, a sharp, capable AI assistant running as a local CLI agent. "
        "You just executed a task for the user. Based on the provided execution logs and context, "
        "tell the user what happened, if it was successful, or if there were any errors. "
        "Be concise, actionable, and slightly witty. If an error occurred, explain what probably went wrong. "
        "Do not just spit out the raw logs, synthesize them intelligently."
    )

    messages = [{"role": "system", "content": system_msg}]
    
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
        response = client.chat.completions.create(
            model=settings.get_model("chat", cognitive_load),
            messages=messages,
            temperature=0.5,
            max_completion_tokens=1024,
        )
        
        from core.budget import get_tracker
        get_tracker().record_usage(response.usage)
        
        return response.choices[0].message.content.strip()

    except Exception as e:
        return f"[error] Failed to generate task response: {e}"
