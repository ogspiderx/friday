"""
config/settings.py — Environment loading, model routing, and global configuration.

Loads .env for API keys, reads groq_api_complete.json for model metadata,
and exposes a clean Settings object used by all other modules.
"""

import os
import json
from pathlib import Path
from dotenv import load_dotenv

# ── Paths ────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"
MODEL_CATALOG_PATH = PROJECT_ROOT / "groq_api_complete.json"
STATE_PATH = PROJECT_ROOT / "state.json"
LOG_PATH = PROJECT_ROOT / "logs" / "session.log"
SKILLS_DIR = PROJECT_ROOT / "skills"
MEMORY_DIR = PROJECT_ROOT / "memory"

# ── Load environment ─────────────────────────────────────────────────────────
load_dotenv(ENV_PATH)


class ModelRouter:
    """
    Selects the right model for each task type.
    
    Strategy:
        fast_model  → intent routing, chat, quick classification (cheap + fast)
        strong_model → planning, command generation, complex reasoning (smart)
    """

    def __init__(self, catalog_path: Path = MODEL_CATALOG_PATH):
        self.catalog = {}
        if catalog_path.exists():
            with open(catalog_path, "r") as f:
                self.catalog = json.load(f)

        # Default model assignments — tuned for Groq's actual offerings
        self.fast_model = "llama-3.1-8b-instant"       # 560 tps, dirt cheap
        self.strong_model = "llama-3.3-70b-versatile"   # 280 tps, much smarter

    def get_model(self, task: str) -> str:
        """Return the appropriate model ID for a given task type."""
        fast_tasks = {"route", "chat", "classify", "match"}
        strong_tasks = {"plan", "shell", "generate", "reason"}

        if task in fast_tasks:
            return self.fast_model
        elif task in strong_tasks:
            return self.strong_model
        else:
            return self.fast_model  # default to fast


class Settings:
    """Global configuration singleton."""

    def __init__(self):
        self.groq_api_key: str = os.getenv("GROQ_API_KEY", "")
        self.openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
        self.project_root: Path = PROJECT_ROOT
        self.state_path: Path = STATE_PATH
        self.log_path: Path = LOG_PATH
        self.skills_dir: Path = SKILLS_DIR
        self.memory_dir: Path = MEMORY_DIR
        self.safe_mode: bool = True
        self.model_router: ModelRouter = ModelRouter()

        # Validate critical config
        if not self.groq_api_key:
            raise EnvironmentError(
                "GROQ_API_KEY not found. Set it in .env or environment."
            )

    def get_model(self, task: str) -> str:
        """Shortcut to model router."""
        return self.model_router.get_model(task)


# ── Module-level singleton ───────────────────────────────────────────────────
_settings: Settings | None = None


def get_settings() -> Settings:
    """Return the global Settings instance (lazy init)."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
