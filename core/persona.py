"""
Self-authored persona files (AGENT.md, HEARTBEAT.md, SOUL.md, USER.md).

Friday may read these for behavior and update them via structured executor actions.
All paths stay under the project root; only allow-listed basenames are writable.
"""

from __future__ import annotations

from pathlib import Path

from config.settings import get_settings

ALLOWED_FILES = frozenset({"AGENT.md", "HEARTBEAT.md", "SOUL.md", "USER.md"})
MAX_FILE_BYTES = 96 * 1024
MAX_CONTEXT_CHARS = 12_000


def _project_root() -> Path:
    return get_settings().project_root


def persona_paths() -> dict[str, Path]:
    root = _project_root()
    return {name: (root / name) for name in sorted(ALLOWED_FILES)}


def read_persona_bundle() -> str:
    """Concatenate persona docs for planner / chat context (truncated)."""
    chunks: list[str] = []
    for name, path in persona_paths().items():
        if not path.is_file():
            continue
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if len(raw) > MAX_CONTEXT_CHARS // len(ALLOWED_FILES):
            raw = raw[: MAX_CONTEXT_CHARS // len(ALLOWED_FILES)] + "\n…(truncated)…\n"
        chunks.append(f"### {name}\n{raw.strip()}")
    if not chunks:
        return ""
    body = "\n\n".join(chunks)
    if len(body) > MAX_CONTEXT_CHARS:
        return body[:MAX_CONTEXT_CHARS] + "\n…(truncated)…\n"
    return body


def write_persona_file(filename: str, content: str, *, append: bool = False) -> dict:
    """
    Write or append to a persona file. Only ALLOWED_FILES in project root.

    Returns: {"ok": bool, "path": str | None, "error": str | None}
    """
    if filename not in ALLOWED_FILES:
        return {"ok": False, "path": None, "error": "filename not in allow-list"}
    if not isinstance(content, str):
        return {"ok": False, "path": None, "error": "content must be a string"}
    root = _project_root().resolve()
    path = (root / filename).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        return {"ok": False, "path": None, "error": "path escapes project root"}
    if path.name != filename:
        return {"ok": False, "path": None, "error": "invalid path"}

    payload = content
    if append and path.is_file():
        try:
            existing = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            existing = ""
        payload = existing + content
    if len(payload.encode("utf-8")) > MAX_FILE_BYTES:
        return {"ok": False, "path": None, "error": f"content exceeds {MAX_FILE_BYTES} bytes"}

    try:
        path.write_text(payload, encoding="utf-8", newline="\n")
    except OSError as e:
        return {"ok": False, "path": str(path), "error": str(e)}
    return {"ok": True, "path": str(path), "error": None}
