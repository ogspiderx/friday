"""
core/critic.py — The Verifier Layer.

A secondary LLM pass that runs after a command executes to verify
if the intended goal was achieved. Identifies silent failures and 
recommends retries.
"""

import json
from groq import Groq
from config.settings import get_settings
import logging

logger = logging.getLogger("friday.critic")

CRITIC_SYSTEM_PROMPT = """You are the Critic Layer for the FRIDAY AI Agent.
Your job is to review the output of an executed shell command or skill and determine if the user's implicit or explicit goal was successfully achieved.

Rules:
1. Examine the `Goal`, `Command`, `Exit Code`, `Stdout`, and `Stderr`.
2. A command might have exit code 0 but still fail semantically (e.g. `grep` found nothing when it should have).
3. Identify silent failures or partial successes.
4. If it failed, determine if a simple retry (with a different command) is recommended.

Output valid JSON only:
{
    "status": "success" | "failure",
    "retry_recommended": true | false,
    "feedback": "brief reasoning"
}"""


class CriticVerifier:
    def __init__(self):
        self._settings = get_settings()
        self.client = Groq(api_key=self._settings.groq_api_key)

    def verify(self, goal: str, command: str, result: dict, cognitive_load: str = "medium") -> dict:
        """
        Verify if an executed command achieved the goal.
        
        Args:
            goal: The original intent or prompt.
            command: The exact command or skill run.
            result: The dict from tools.shell.execute() containing stdout/stderr/exit_code.
            
        Returns:
            dict with 'status', 'retry_recommended', and 'feedback'
        """
        prompt = (
            f"Goal: {goal}\n"
            f"Command Executed: {command}\n"
            f"Exit Code: {result.get('exit_code', -1)}\n"
            f"Stdout: {result.get('stdout', '')[:1000]}\n"
            f"Stderr: {result.get('stderr', '')[:500]}\n"
        )

        try:
            response = self.client.chat.completions.create(
                model=self._settings.get_model("reason", cognitive_load),
                messages=[
                    {"role": "system", "content": CRITIC_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_completion_tokens=200,
                response_format={"type": "json_object"},
            )
            
            from core.budget import get_tracker
            get_tracker().record_usage(response.usage)

            raw = response.choices[0].message.content.strip()
            evaluation = json.loads(raw)
            
            # Sanitize fallback
            if "status" not in evaluation:
                evaluation["status"] = "success" if result.get("exit_code") == 0 else "failure"
            if "retry_recommended" not in evaluation:
                evaluation["retry_recommended"] = False
                
            return evaluation

        except Exception as e:
            logger.error(f"Critic failure: {e}")
            # Fail open — assume success if verification crashes unless exit code is bad
            return {
                "status": "success" if result.get("exit_code", -1) == 0 else "failure",
                "retry_recommended": False,
                "feedback": f"Critic error: {e}"
            }
