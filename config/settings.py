"""
config/settings.py — Environment loading, model routing, and global configuration.

Loads .env for API keys, reads groq_api_complete.json to discover reasoning-capable
production models, and exposes Settings + per-turn model resolution (cognitive_load).
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
    Selects models using groq_api_complete.json plus optional env overrides.

    A lightweight router pass labels each turn with cognitive_load (low / medium / high).
    That label picks among fast, strong, and reasoning-tier models discovered in the catalog.
    """

    def __init__(self, catalog_path: Path = MODEL_CATALOG_PATH):
        self.catalog: dict = {}
        if catalog_path.exists():
            with open(catalog_path, "r") as f:
                self.catalog = json.load(f)

        reasoning_chain = self._reasoning_model_chain()

        # Defaults can be overridden per deployment (e.g. if a reasoning ID is unavailable).
        self.fast_model = os.getenv("FRIDAY_MODEL_FAST", "llama-3.1-8b-instant")
        self.strong_model = os.getenv("FRIDAY_MODEL_STRONG", "llama-3.3-70b-versatile")
        self.reason_model = os.getenv(
            "FRIDAY_MODEL_REASON",
            reasoning_chain[0] if reasoning_chain else self.strong_model,
        )
        self.reason_deep_model = os.getenv(
            "FRIDAY_MODEL_REASON_DEEP",
            reasoning_chain[-1] if reasoning_chain else self.strong_model,
        )

    @staticmethod
    def _reasoning_supported(capabilities: dict | None) -> bool:
        if not capabilities:
            return False
        r = capabilities.get("reasoning")
        if isinstance(r, dict):
            return bool(r.get("supported"))
        return r is True

    def _reasoning_model_chain(self) -> list[str]:
        """
        Ordered list of production text models that advertise structured reasoning
        in the bundled Groq catalog (smaller / cheaper first when detectable).
        """
        ids: list[str] = []
        for m in self.catalog.get("models", {}).get("production", []):
            if m.get("type") != "text-to-text":
                continue
            outs = (m.get("modality") or {}).get("output") or []
            if "text" not in outs:
                continue
            if self._reasoning_supported(m.get("capabilities")):
                ids.append(m["id"])

        def _rank(mid: str) -> tuple[int, str]:
            mid_l = mid.lower()
            if "20b" in mid_l and "120" not in mid_l:
                return (0, mid)
            if "120b" in mid_l:
                return (1, mid)
            return (2, mid)

        ids.sort(key=_rank)
        # De-duplicate while preserving order
        seen: set[str] = set()
        out: list[str] = []
        for i in ids:
            if i not in seen:
                seen.add(i)
                out.append(i)
        return out

    def resolve_model(self, task: str, cognitive_load: str = "medium") -> str:
        """
        Map a logical task to a concrete Groq model id.

        task:
            route | chat | plan | reason | generate | shell | classify | match
        cognitive_load:
            low | medium | high (from the intent router)
        """
        tier = cognitive_load if cognitive_load in ("low", "medium", "high") else "medium"

        if task in ("route", "classify", "match"):
            return self.fast_model

        if task == "chat":
            if tier == "low":
                return self.fast_model
            if tier == "medium":
                return self.strong_model
            return self.reason_model

        if task == "plan":
            if tier == "high":
                return self.reason_deep_model
            return self.strong_model

        if task in ("reason", "generate", "shell"):
            if tier == "high":
                return self.reason_model
            return self.strong_model

        return self.strong_model

    def get_model(self, task: str, cognitive_load: str | None = None) -> str:
        """Backward-compatible entry: cognitive_load defaults to medium."""
        return self.resolve_model(task, cognitive_load or "medium")


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

    def get_model(self, task: str, cognitive_load: str | None = None) -> str:
        """Shortcut to model router (optional per-turn cognitive_load)."""
        return self.model_router.get_model(task, cognitive_load)


# ── Module-level singleton ───────────────────────────────────────────────────
_settings: Settings | None = None


def get_settings() -> Settings:
    """Return the global Settings instance (lazy init)."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
