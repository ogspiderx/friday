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

Also set cognitive_load for downstream model selection (NOT the same as intent):
- "low" — trivial, social, or very short prompts where mistakes are low-stakes
- "medium" — default when unsure; ordinary questions and single-step tasks
- "high" — needs careful reasoning or reliably correct facts: math, calendars/timezones,
  security/safety, multi-step logic, ambiguity, long prompts, or precise system state

Use "high" when the user expects an exact factual answer about the real world or this machine
(current time in a named zone, file paths, hardware, etc.) even if the tone is conversational.

Respond with ONLY valid JSON, no markdown, no explanation:
{"intent": "<intent>", "confidence": <0.0-1.0>, "cognitive_load": "low|medium|high"}"""


def classify_intent(user_input: str) -> dict:
    """
    Classify user input into an intent category.
    
    Args:
        user_input: Raw text from the user.
    
    Returns:
        dict with 'intent' (str), 'confidence' (float), and 'cognitive_load' ("low"|"medium"|"high").
        Falls back to a safe default on error.
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

        load = result.get("cognitive_load", "medium")
        if load not in ("low", "medium", "high"):
            load = "medium"
        result["cognitive_load"] = load

        valid_intents = {"chat", "shell_task", "skill_task", "memory_query"}
        if result["intent"] not in valid_intents:
            result["intent"] = "chat"

        return result

    except Exception as e:
        return {"intent": "chat", "confidence": 0.3, "cognitive_load": "medium", "error": str(e)}
