"""
core/router.py — Intent classification via Groq LLM.

Takes raw user input and classifies it into one of:
  - chat          → conversational, no action needed
  - shell_task    → requires shell command execution
  - skill_task    → matches a known skill
  - memory_query  → user is asking about past context

Uses the fast model for speed. Returns structured JSON.
"""

import json
from groq import Groq
from config.settings import get_settings

ROUTER_SYSTEM_PROMPT = """You are an intent classifier for a CLI AI agent named FRIDAY.

Classify the user's input into exactly ONE of these intents:
- "chat" — casual conversation, greetings, questions about yourself, opinions
- "shell_task" — user wants to run a shell command, manage files, install packages, system operations
- "skill_task" — user wants to perform a structured task (e.g. git operations, project scaffolding, code analysis)
- "memory_query" — user is asking about something from a previous conversation or past context

Respond with ONLY valid JSON, no markdown, no explanation:
{"intent": "<intent>", "confidence": <0.0-1.0>}"""


def classify_intent(user_input: str) -> dict:
    """
    Classify user input into an intent category.
    
    Args:
        user_input: Raw text from the user.
    
    Returns:
        dict with 'intent' (str) and 'confidence' (float).
        Falls back to {"intent": "chat", "confidence": 0.5} on error.
    """
    settings = get_settings()
    client = Groq(api_key=settings.groq_api_key)

    try:
        response = client.chat.completions.create(
            model=settings.get_model("route"),
            messages=[
                {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
                {"role": "user", "content": user_input},
            ],
            temperature=0.1,
            max_completion_tokens=100,
            response_format={"type": "json_object"},
        )
        
        from core.budget import get_tracker
        get_tracker().record_usage(response.usage)

        raw = response.choices[0].message.content.strip()
        result = json.loads(raw)

        # Validate structure
        if "intent" not in result:
            result["intent"] = "chat"
        if "confidence" not in result:
            result["confidence"] = 0.5

        # Clamp confidence
        result["confidence"] = max(0.0, min(1.0, float(result["confidence"])))

        valid_intents = {"chat", "shell_task", "skill_task", "memory_query"}
        if result["intent"] not in valid_intents:
            result["intent"] = "chat"

        return result

    except Exception as e:
        return {"intent": "chat", "confidence": 0.3, "error": str(e)}
