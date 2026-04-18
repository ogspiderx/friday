"""
tools/shell.py — Safe shell command execution.

Prefers argv + shell=False for structured commands; falls back to validated
shell strings only when needed. Integrates with the safety policy.
"""

from __future__ import annotations

import os
import shlex
import subprocess
from typing import Sequence

from safety.policy import SafetyPolicy
from core.ui import console


class ShellExecutor:
    """
    Secure shell execution engine.

    Pipeline:
        1. Validate via SafetyPolicy (on a canonical command line)
        2. Prompt for confirmation if required
        3. Execute via subprocess (shell=False when using argv)
    """

    def __init__(self):
        self._policy = SafetyPolicy()

    def execute_argv(
        self,
        argv: Sequence[str],
        cwd: str | None = None,
        skip_confirm: bool = False,
    ) -> dict:
        """Execute with argument vector (no shell interpolation). Preferred path."""
        argv = [str(a) for a in argv]
        if not argv or not argv[0]:
            return {
                "stdout": "",
                "stderr": "Empty argv.",
                "exit_code": -1,
                "executed": False,
                "risk": "safe",
            }
        if any("\x00" in a for a in argv):
            return {
                "stdout": "",
                "stderr": "Rejected: NUL in argument.",
                "exit_code": -1,
                "executed": False,
                "risk": "dangerous",
            }
        cmd_line = shlex.join(argv)
        validation = self._policy.validate_command(cmd_line)
        if not validation["allowed"]:
            return {
                "stdout": "",
                "stderr": validation["reason"],
                "exit_code": -1,
                "executed": False,
                "risk": validation["risk"],
            }

        risk = validation["risk"]
        _, color = self._policy.get_risk_display(risk)

        if validation["requires_confirmation"] and not skip_confirm:
            console.print(f"  [{color}]{risk}[/]: {cmd_line}")
            console.print(f"  [friday.dim]{validation['reason']}[/friday.dim]")
            try:
                confirm = console.input("[friday.warn]  ok? (y/n): [/friday.warn]").strip().lower()
            except (EOFError, KeyboardInterrupt):
                confirm = "n"
            if confirm not in ("y", "yes"):
                return {
                    "stdout": "",
                    "stderr": "Command cancelled by user.",
                    "exit_code": -1,
                    "executed": False,
                    "risk": risk,
                }

        work_dir = cwd or os.getcwd()
        env = os.environ.copy()
        for k in ("LD_PRELOAD", "LD_LIBRARY_PATH", "PROMPT_COMMAND", "BASH_ENV", "ENV"):
            env.pop(k, None)

        try:
            result = subprocess.run(
                list(argv),
                shell=False,
                cwd=work_dir,
                env=env,
                capture_output=True,
                text=True,
                timeout=120,
            )
            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode,
                "executed": True,
                "risk": risk,
            }
        except subprocess.TimeoutExpired:
            return {
                "stdout": "",
                "stderr": "Command timed out after 120 seconds.",
                "exit_code": -1,
                "executed": False,
                "risk": risk,
            }
        except Exception as e:
            return {
                "stdout": "",
                "stderr": f"Execution error: {e}",
                "exit_code": -1,
                "executed": False,
                "risk": risk,
            }

    def execute(self, command: str, cwd: str | None = None, skip_confirm: bool = False) -> dict:
        """
        Legacy string entrypoint. Prefer execute_argv from structured callers.

        Uses shell=True only for this path (validated string).
        """
        command = command.strip()
        if not command:
            return {
                "stdout": "",
                "stderr": "Empty command.",
                "exit_code": -1,
                "executed": False,
                "risk": "safe",
            }

        # If it is a simple token list, upgrade to argv execution (no shell).
        try:
            parts = shlex.split(command, posix=True)
        except ValueError:
            parts = []

        if parts and command == shlex.join(parts):
            return self.execute_argv(parts, cwd=cwd, skip_confirm=skip_confirm)

        validation = self._policy.validate_command(command)
        if not validation["allowed"]:
            return {
                "stdout": "",
                "stderr": validation["reason"],
                "exit_code": -1,
                "executed": False,
                "risk": validation["risk"],
            }

        risk = validation["risk"]
        _, color = self._policy.get_risk_display(risk)

        if validation["requires_confirmation"] and not skip_confirm:
            console.print(f"  [{color}]{risk}[/]: {command}")
            console.print(f"  [friday.dim]{validation['reason']}[/friday.dim]")
            try:
                confirm = console.input("[friday.warn]  ok? (y/n): [/friday.warn]").strip().lower()
            except (EOFError, KeyboardInterrupt):
                confirm = "n"
            if confirm not in ("y", "yes"):
                return {
                    "stdout": "",
                    "stderr": "Command cancelled by user.",
                    "exit_code": -1,
                    "executed": False,
                    "risk": risk,
                }

        work_dir = cwd or os.getcwd()
        env = os.environ.copy()
        for k in ("LD_PRELOAD", "LD_LIBRARY_PATH", "PROMPT_COMMAND", "BASH_ENV", "ENV"):
            env.pop(k, None)

        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=work_dir,
                env=env,
                capture_output=True,
                text=True,
                timeout=120,
            )
            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode,
                "executed": True,
                "risk": risk,
            }
        except subprocess.TimeoutExpired:
            return {
                "stdout": "",
                "stderr": "Command timed out after 120 seconds.",
                "exit_code": -1,
                "executed": False,
                "risk": risk,
            }
        except Exception as e:
            return {
                "stdout": "",
                "stderr": f"Execution error: {e}",
                "exit_code": -1,
                "executed": False,
                "risk": risk,
            }
