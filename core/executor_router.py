"""
core/executor_router.py

Structured command routing: native filesystem primitives, persona file writes,
and argv-based shell execution (no shell interpolation for mapped commands).
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from tools.shell import ShellExecutor
from core.persona import write_persona_file

_MAX_READ_BYTES = 2_000_000
_MAX_WRITE_BYTES = 512_000
_ARG_FORBIDDEN = frozenset(";|&$`<>\n\r\x00")


class ExecutorRouter:
    def __init__(self):
        self.shell = ShellExecutor()

    def execute(self, command_spec: dict, default_cwd: str | None = None) -> dict:
        """
        Routes and executes a structured command dictionary.

        Returns:
            dict with stdout, stderr, exit_code, executed, skill_name
        """
        cmd_type = command_spec.get("type", "unknown")

        if cmd_type == "filesystem":
            return self._execute_filesystem_native(
                command_spec.get("action", ""),
                command_spec.get("params") or {},
                default_cwd,
            )

        if cmd_type == "persona":
            return self._execute_persona(command_spec.get("action", ""), command_spec.get("params") or {})

        if cmd_type in ("git", "package", "system", "shell"):
            return self._execute_shell_mapped(command_spec, default_cwd)

        return self._execute_shell_mapped(command_spec, default_cwd)

    def _within_workspace(self, work: Path, target: Path) -> bool:
        try:
            target.resolve().relative_to(work.resolve())
            return True
        except ValueError:
            return False

    def _execute_filesystem_native(self, action: str, params: dict, default_cwd: str | None) -> dict:
        work_dir = Path(default_cwd or os.getcwd()).resolve()
        path_str = params.get("path", "") or "."
        target = (work_dir / path_str).resolve()

        if not self._within_workspace(work_dir, target):
            return self._failure("Path escapes workspace boundary (filesystem).")

        try:
            if action == "create_directory":
                target.mkdir(parents=True, exist_ok=True)
                return self._success(f"Directory created: {target}", "")

            if action == "delete":
                if not target.exists():
                    return self._success(f"Path does not exist: {target}", "")
                recursive = params.get("recursive", False)
                if target.is_dir():
                    if recursive:
                        shutil.rmtree(target)
                        return self._success(f"Directory tree deleted: {target}", "")
                    target.rmdir()
                    return self._success(f"Empty directory deleted: {target}", "")
                target.unlink()
                return self._success(f"File deleted: {target}", "")

            if action == "create_file":
                content = params.get("content", "")
                if not isinstance(content, str):
                    return self._failure("create_file content must be a string")
                if len(content.encode("utf-8")) > _MAX_WRITE_BYTES:
                    return self._failure("create_file content too large")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8", newline="\n")
                return self._success(f"File written: {target}", "")

            if action == "read_file":
                if not target.exists() or not target.is_file():
                    return self._failure(f"File does not exist: {target}")
                size = target.stat().st_size
                if size > _MAX_READ_BYTES:
                    return self._failure("File too large to read via agent")
                content = target.read_text(encoding="utf-8", errors="replace")
                return self._success(content, "")

            return self._failure(f"Unsupported filesystem action: {action}")

        except Exception as e:
            return self._failure(f"Native FS Error: {str(e)}")

    def _execute_persona(self, action: str, params: dict) -> dict:
        if action not in ("write", "append"):
            return self._failure("persona action must be write or append")
        filename = params.get("file") or params.get("filename")
        content = params.get("content", "")
        if not isinstance(filename, str) or not isinstance(content, str):
            return self._failure("persona requires string file and content")
        res = write_persona_file(filename, content, append=action == "append")
        if res["ok"]:
            return self._success(f"Updated {filename}", "")
        return self._failure(res.get("error") or "persona write failed")

    def _argv_from_spec(self, command_spec: dict) -> list[str] | None:
        cmd_type = command_spec.get("type", "unknown")
        action = command_spec.get("action", "") or ""
        params = command_spec.get("params") or {}
        raw_args = params.get("args") if isinstance(params.get("args"), list) else []

        def _clean_segments(segments: list[str]) -> list[str] | None:
            out: list[str] = []
            for seg in segments:
                if not isinstance(seg, str) or not seg.strip():
                    return None
                if any(ch in seg for ch in _ARG_FORBIDDEN):
                    return None
                out.append(seg)
            return out

        argv: list[str] = []

        if cmd_type == "git":
            argv = ["git", str(action)]
            argv.extend(str(a) for a in raw_args)

        elif cmd_type in ("package", "system"):
            if "binary" in params and isinstance(params["binary"], str):
                argv = [params["binary"], str(action)]
            else:
                argv = [str(action)]
            argv.extend(str(a) for a in raw_args)

        elif cmd_type == "shell":
            argv = [str(action)]
            argv.extend(str(a) for a in raw_args)

        else:
            argv = [str(action)]
            argv.extend(str(a) for a in raw_args)

        cleaned = _clean_segments(argv)
        if not cleaned or not cleaned[0]:
            return None
        return cleaned

    def _execute_shell_mapped(self, command_spec: dict, default_cwd: str | None) -> dict:
        argv = self._argv_from_spec(command_spec)
        if not argv:
            return self._failure("Invalid structured shell command (check argv / metacharacters).")
        return self.shell.execute_argv(argv, cwd=default_cwd or os.getcwd())

    def _success(self, stdout: str, stderr: str = "") -> dict:
        return {
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": 0,
            "executed": True,
            "skill_name": "python_native",
        }

    def _failure(self, error: str) -> dict:
        return {
            "stdout": "",
            "stderr": error,
            "exit_code": 1,
            "executed": True,
            "skill_name": "python_native",
        }
