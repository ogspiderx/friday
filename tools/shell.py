"""
tools/shell.py — Safe shell command execution.

Executes commands via subprocess (never os.system), captures stdout/stderr/exit_code,
integrates with the safety policy for risk-based confirmation flow.
"""

import subprocess
import os
from safety.policy import SafetyPolicy
from config.settings import get_settings
from rich.console import Console
from rich.panel import Panel

console = Console()


class ShellExecutor:
    """
    Secure shell execution engine.
    
    Pipeline:
        1. Receive command
        2. Validate via SafetyPolicy
        3. Prompt for confirmation if required
        4. Execute via subprocess
        5. Return structured result
    """

    def __init__(self):
        self._policy = SafetyPolicy()
        self._settings = get_settings()

    def execute(self, command: str, cwd: str | None = None, skip_confirm: bool = False) -> dict:
        """
        Execute a shell command safely.
        
        Args:
            command: Shell command string to execute.
            cwd: Working directory (defaults to current).
            skip_confirm: If True, bypass confirmation (use with care).
        
        Returns:
            dict with stdout, stderr, exit_code, executed (bool), risk.
        """
        # Step 1: Validate
        validation = self._policy.validate_command(command)

        if not validation["allowed"]:
            return {
                "stdout": "",
                "stderr": validation["reason"],
                "exit_code": -1,
                "executed": False,
                "risk": validation["risk"],
            }

        # Step 2: Display risk and confirm if needed
        risk = validation["risk"]
        emoji, color = self._policy.get_risk_display(risk)

        if validation["requires_confirmation"] and not skip_confirm:
            console.print(
                Panel(
                    f"[bold]{command}[/bold]",
                    title=f"{emoji} [{color}]{risk.upper()} RISK[/{color}]",
                    border_style=color,
                )
            )
            console.print(f"  [dim]{validation['reason']}[/dim]")

            try:
                confirm = console.input("[bold yellow]  Execute? (y/n): [/bold yellow]").strip().lower()
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

        # Step 3: Execute
        work_dir = cwd or os.getcwd()

        try:
            # Sanitize environment to prevent environment variable injection payloads
            env = os.environ.copy()
            dangerous_env_keys = ["LD_PRELOAD", "LD_LIBRARY_PATH", "PROMPT_COMMAND", "BASH_ENV", "ENV"]
            for k in dangerous_env_keys:
                env.pop(k, None)

            result = subprocess.run(
                command,
                shell=True,
                cwd=work_dir,
                env=env,
                capture_output=True,
                text=True,
                timeout=120,  # 2 minute timeout
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
