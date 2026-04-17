"""
core/state.py — Persistent agent state.

Maintains a JSON-backed state file that survives across sessions.
Tracks working directory, last command, safe mode toggle, and 
session metadata.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from config.settings import get_settings


DEFAULT_STATE = {
    "current_directory": os.getcwd(),
    "last_command": None,
    "safe_mode": True,
    "mode": "safe",  # safe | auto | build
    "session_started": None,
    "total_commands": 0,
}


class AgentState:
    """
    Persistent state manager backed by state.json.
    
    Loads existing state on init, saves after every mutation.
    All fields are accessible as dict keys or via helper methods.
    """

    def __init__(self):
        self._settings = get_settings()
        self._path: Path = self._settings.state_path
        self._data: dict = {}
        self._load()

    def _load(self):
        """Load state from disk, or create defaults."""
        if self._path.exists():
            try:
                with open(self._path, "r") as f:
                    self._data = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._data = dict(DEFAULT_STATE)
        else:
            self._data = dict(DEFAULT_STATE)

        # Always stamp session start
        if not self._data.get("session_started"):
            self._data["session_started"] = datetime.now().isoformat()
            self._save()

    def _save(self):
        """Persist state to disk."""
        with open(self._path, "w") as f:
            json.dump(self._data, f, indent=2, default=str)

    # ── Accessors ────────────────────────────────────────────────────────

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value):
        self._data[key] = value
        self._save()

    @property
    def safe_mode(self) -> bool:
        return self._data.get("safe_mode", True)

    @safe_mode.setter
    def safe_mode(self, value: bool):
        self._data["safe_mode"] = value
        if value:
            self.mode = "safe" # Force mode sync
        self._save()
        
    @property
    def mode(self) -> str:
        return self._data.get("mode", "safe")
        
    @mode.setter
    def mode(self, value: str):
        if value in ("safe", "auto", "build"):
            self._data["mode"] = value
            self._save()

    @property
    def current_directory(self) -> str:
        return self._data.get("current_directory", os.getcwd())

    @property
    def last_command(self) -> str | None:
        return self._data.get("last_command")

    def record_command(self, command: str):
        """Record that a command was executed."""
        self._data["last_command"] = command
        self._data["total_commands"] = self._data.get("total_commands", 0) + 1
        self._save()

    def to_dict(self) -> dict:
        return dict(self._data)
