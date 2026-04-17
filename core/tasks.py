"""
core/tasks.py — Persistent goal management.

Tracks long-running or multi-step tasks across sessions.
"""

import json
from pathlib import Path
from dataclasses import dataclass, field, asdict
from datetime import datetime
from config.settings import get_settings
import uuid

@dataclass
class Task:
    goal: str
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    status: str = "pending"  # pending | running | done | failed
    steps: list[str] = field(default_factory=list)
    retries: int = 0
    max_retries: int = 3
    locked_at: str | None = None
    last_run: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

class TaskManager:
    """Manages persistent list of tasks in tasks.json."""
    
    def __init__(self):
        settings = get_settings()
        self._path = settings.project_root / "tasks.json"
        self._tasks: dict[str, Task] = {}
        self._load()
        
    def _load(self):
        if self._path.exists():
            try:
                with open(self._path, "r") as f:
                    data = json.load(f)
                    for k, v in data.items():
                        self._tasks[k] = Task(**v)
            except Exception:
                self._tasks = {}

    def _save(self):
        data = {k: asdict(v) for k, v in self._tasks.items()}
        with open(self._path, "w") as f:
            json.dump(data, f, indent=2)
            
    def add_task(self, goal: str) -> Task:
        t = Task(goal=goal)
        self._tasks[t.id] = t
        self._save()
        return t
        
    def complete(self, task_id: str):
        if task_id in self._tasks:
            self._tasks[task_id].status = "done"
            self._tasks[task_id].locked_at = None
            self._tasks[task_id].last_run = datetime.now().isoformat()
            self._save()
            
    def fail(self, task_id: str):
        if task_id in self._tasks:
            t = self._tasks[task_id]
            t.retries += 1
            if t.retries >= t.max_retries:
                 t.status = "failed"
            else:
                 t.status = "pending" # Back off to pending queue for another try

            t.locked_at = None
            t.last_run = datetime.now().isoformat()
            self._save()
            
    def lock(self, task_id: str):
        """Acquires a lease on the task so it isn't double-executed in multi-loop scenarios."""
        if task_id in self._tasks:
            self._tasks[task_id].status = "running"
            self._tasks[task_id].locked_at = datetime.now().isoformat()
            self._save()
            
    def release_stale_locks(self, timeout_seconds: int = 300):
        """Frees tasks stuck in running after a crash."""
        now = datetime.now()
        for t in self._tasks.values():
            if t.status == "running" and t.locked_at:
                try:
                    locked = datetime.fromisoformat(t.locked_at)
                    if (now - locked).total_seconds() > timeout_seconds:
                         t.status = "pending"
                         t.locked_at = None
                         self._save()
                except ValueError:
                    continue
            
    def get_pending(self) -> list[Task]:
        return [t for t in self._tasks.values() if t.status == "pending"]
        
    def all_tasks(self) -> list[Task]:
        return list(self._tasks.values())
