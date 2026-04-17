"""
core/budget.py

Token and Cost Tracking.
Stores running totals of token usage to prevent runaway systems
and signals when the agent should throttle reasoning depth.
"""

import json
from pathlib import Path
from config.settings import get_settings

class TokenTracker:
    def __init__(self):
        settings = get_settings()
        self._path = settings.project_root / "budget.json"
        
        # Hard limits per session / lifetime for safety
        self.MAX_TOKENS_SOFT_LIMIT = 50000 
        
        self.stats = {
            "prompt_tokens_total": 0,
            "completion_tokens_total": 0,
            "total_tokens": 0,
            "requests_count": 0
        }
        self._load()
        
    def _load(self):
        if self._path.exists():
            try:
                with open(self._path, "r") as f:
                    data = json.load(f)
                    self.stats.update(data)
            except Exception:
                pass

    def _save(self):
        try:
            with open(self._path, "w") as f:
                json.dump(self.stats, f, indent=2)
        except Exception:
            pass

    def record_usage(self, usage) -> None:
        """
        Record usage from a Groq CompletionUsage object.
        usage shape implies: usage.prompt_tokens, usage.completion_tokens, usage.total_tokens
        """
        if not usage:
            return
            
        try:
            self.stats["prompt_tokens_total"] += getattr(usage, "prompt_tokens", 0)
            self.stats["completion_tokens_total"] += getattr(usage, "completion_tokens", 0)
            self.stats["total_tokens"] += getattr(usage, "total_tokens", 0)
            self.stats["requests_count"] += 1
            self._save()
        except AttributeError:
            pass

    def get_budget_status(self) -> dict:
        """
        Returns info about budget health.
        If we cross the soft limit, we should downgrade the model
        and bypass optional LLM passes (like the Critic).
        """
        total = self.stats["total_tokens"]
        exceeded = total >= self.MAX_TOKENS_SOFT_LIMIT
        
        return {
            "total_tokens": total,
            "limit": self.MAX_TOKENS_SOFT_LIMIT,
            "exceeded": exceeded,
            "throttle_recommended": exceeded
        }

# Global singleton so we don't reload disk on every API call
_tracker = TokenTracker()

def get_tracker() -> TokenTracker:
    return _tracker
