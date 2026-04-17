"""
memory/mempalace_client.py — Long-term persistent memory (MemPalace).

Stores important outcomes, user preferences, and learned patterns
to a JSON-backed file that persists across sessions.

This is the "long-term memory" complement to session.py's short-term memory.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from config.settings import get_settings


MEMPALACE_FILE = "mempalace.json"


class MemPalaceClient:
    """
    Long-term memory storage for FRIDAY.
    
    Memory types:
        - fact      → learned facts about the user or system
        - outcome   → results of past executions worth remembering
        - preference → user preferences and patterns
        - note      → explicit notes the user asked to remember
    """

    def __init__(self):
        settings = get_settings()
        self._path = settings.project_root / MEMPALACE_FILE
        self._memories: list[dict] = []
        self._load()

    def _load(self):
        """Load memories from disk."""
        if self._path.exists():
            try:
                with open(self._path, "r") as f:
                    data = json.load(f)
                    self._memories = data.get("memories", [])
            except (json.JSONDecodeError, IOError):
                self._memories = []

    def _save(self):
        """Persist memories to disk."""
        data = {
            "version": 1,
            "updated_at": datetime.now().isoformat(),
            "count": len(self._memories),
            "memories": self._memories,
        }
        with open(self._path, "w") as f:
            json.dump(data, f, indent=2, default=str)

    def store(self, content: str, memory_type: str = "outcome", tags: list[str] | None = None):
        """
        Store a new memory.
        
        Args:
            content: The memory content.
            memory_type: One of "fact", "outcome", "preference", "note".
            tags: Optional tags for retrieval.
        """
        entry = {
            "id": len(self._memories) + 1,
            "timestamp": datetime.now().isoformat(),
            "type": memory_type,
            "content": content,
            "tags": tags or [],
        }
        self._memories.append(entry)
        self._save()

    def recall(self, query: str, max_results: int = 5) -> list[dict]:
        """
        Recall memories relevant to a query.
        
        Uses keyword matching across content and tags.
        
        Args:
            query: Search query.
            max_results: Maximum number of results.
        
        Returns:
            List of matching memory dicts, most relevant first.
        """
        query_words = set(query.lower().split())
        scored = []

        for mem in self._memories:
            score = 0
            content_words = set(mem["content"].lower().split())
            score += len(query_words & content_words) * 2

            tag_words = set(t.lower() for t in mem.get("tags", []))
            score += len(query_words & tag_words) * 3

            if score > 0:
                scored.append((score, mem))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [mem for _, mem in scored[:max_results]]

    def recall_context_string(self, query: str, max_results: int = 3) -> str:
        """
        Build a context string from relevant long-term memories.
        
        Returns formatted string for LLM consumption.
        """
        memories = self.recall(query, max_results)
        if not memories:
            return ""

        parts = []
        for mem in memories:
            parts.append(f"[{mem['type']}] {mem['content'][:200]}")

        return "\n".join(parts)

    def get_all(self) -> list[dict]:
        """Return all stored memories."""
        return list(self._memories)

    def clear(self):
        """Clear all long-term memories."""
        self._memories.clear()
        self._save()

    @property
    def count(self) -> int:
        return len(self._memories)
