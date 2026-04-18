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
import re

from groq import Groq
from config.settings import get_settings
from core.groq_compat import chat_completion_create

def _is_present_time_or_date_question(text: str) -> bool:
    """True when the user is asking for now's time/day/date (not recall of past chat)."""
    s = text.lower().strip()
    if not s:
        return False
    phrases = (
        r"what\s+is\s+the\s+time",
        r"what'?s\s+the\s+time",
        r"what\s+time\s+is\s+it",
        r"time\s*rn\b",
        r"current\s+time",
        r"what\s+is\s+the\s+day",
        r"what\s+day\s+is\s+it",
        r"what'?s\s+the\s+day",
        r"what\s+is\s+the\s+date",
        r"what\s+date\s+is\s+it",
        r"what'?s\s+the\s+date",
        r"today'?s?\s+date",
        r"current\s+date",
    )
    for p in phrases:
        if re.search(p, s):
            return True
    m = re.search(r"\bwhat\s+time\b", s)
    if m:
        rest = s[m.end() :].lstrip()
        if not rest.startswith(
            ("did ", "does ", "do ", "was ", "were ", "have ", "had ", "will ", "would ", "should ")
        ):
            return True
    m = re.search(r"\bwhat\s+day\b", s)
    if m:
        rest = s[m.end() :].lstrip()
        if not rest.startswith(("did ", "was ", "were ", "have ", "had ")):
            return True
    return False


def _override_false_memory_query(user_input: str, result: dict) -> dict:
    """
    Present-moment clock/calendar questions must not use memory_query
    (that path only searches stored snippets and confuses users).
    """
    if result.get("intent") != "memory_query":
        return result
    if not _is_present_time_or_date_question(user_input):
        return result
    out = dict(result)
    out["intent"] = "shell_task"
    out["cognitive_load"] = "high"
    out["confidence"] = max(float(out.get("confidence", 0.7)), 0.85)
    return out


ROUTER_SYSTEM_PROMPT = """You are an intent classifier for a CLI copilot named Friday.

Classify the user's input into exactly ONE of these intents:
- "chat" — casual conversation, greetings, opinions, general questions that do NOT ask to recall prior chat
- "shell_task" — run something on the machine: files, packages, processes, OR factual readouts (disk, time via `date`, network ping, etc.)
- "skill_task" — structured project/dev workflows (git, builds, scaffolding) when a repeatable skill fits
- "memory_query" — ONLY when the user explicitly wants prior conversation recalled (e.g. "what did I say about…", "remind me what we…", "last time you…", "did I already tell you…"). NEVER use memory_query for the current time, today's date, weather, math, or generic trivia.

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
        pm = settings.get_model("route")

        def _route_kw(mid: str):
            return {
                "messages": [
                    {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
                    {"role": "user", "content": user_input},
                ],
                "temperature": 0.1,
                "max_completion_tokens": 150,
                "response_format": {"type": "json_object"},
            }

        response = chat_completion_create(client, primary_model=pm, builder=_route_kw)
        
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

        result = _override_false_memory_query(user_input, result)

        return result

    except Exception as e:
        return {"intent": "chat", "confidence": 0.3, "cognitive_load": "medium", "error": str(e)}
