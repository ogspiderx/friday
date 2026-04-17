"""
memory/session.py — Short-term session memory.

Maintains an in-memory conversation history for the current session.
Provides context retrieval for the planner and router.
"""

from datetime import datetime
from dataclasses import dataclass, field


@dataclass
class MemoryEntry:
    """A single memory entry."""
    timestamp: str
    role: str           # "user" | "assistant" | "system"
    content: str
    intent: str = ""
    metadata: dict = field(default_factory=dict)


class SessionMemory:
    """
    Short-term memory for the current FRIDAY session.
    
    Stores conversation turns and execution results.
    Provides context retrieval for planning.
    """

    def __init__(self, max_entries: int = 50):
        self._entries: list[MemoryEntry] = []
        self._max_entries = max_entries

    def add(self, role: str, content: str, intent: str = "", metadata: dict | None = None):
        """Add a memory entry."""
        entry = MemoryEntry(
            timestamp=datetime.now().isoformat(),
            role=role,
            content=content,
            intent=intent,
            metadata=metadata or {},
        )
        self._entries.append(entry)

        # Trim oldest if over limit
        if len(self._entries) > self._max_entries:
            self._entries = self._entries[-self._max_entries:]

    def get_recent(self, n: int = 5) -> list[MemoryEntry]:
        """Get the N most recent entries."""
        return self._entries[-n:]

    def get_context_string(self, n: int = 5) -> str:
        """
        Build a context string from recent memory for LLM consumption.
        
        Returns a formatted string of the last N exchanges.
        """
        recent = self.get_recent(n)
        if not recent:
            return ""

        parts = []
        for entry in recent:
            prefix = "User" if entry.role == "user" else "FRIDAY"
            parts.append(f"[{prefix}]: {entry.content[:200]}")

        return "\n".join(parts)

    def search(self, query: str, max_results: int = 3) -> list[MemoryEntry]:
        """
        Simple keyword search through memory entries.
        
        Args:
            query: Search terms.
            max_results: Maximum number of results.
        
        Returns:
            Matching memory entries, most recent first.
        """
        query_words = set(query.lower().split())
        scored = []

        for entry in self._entries:
            content_words = set(entry.content.lower().split())
            overlap = len(query_words & content_words)
            if overlap > 0:
                scored.append((overlap, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [entry for _, entry in scored[:max_results]]

    def clear(self):
        """Clear all session memory."""
        self._entries.clear()

    @property
    def size(self) -> int:
        return len(self._entries)
