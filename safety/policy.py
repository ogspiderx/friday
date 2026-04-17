"""
safety/policy.py — Centralized safety policy enforcement.

Validates commands before execution, classifies risk levels,
and enforces workspace restrictions. This is the gatekeeper
that sits between the planner and the shell executor.

Risk Levels:
  - safe     → auto-execute
  - medium   → warn but execute
  - dangerous → require explicit user confirmation
"""

import re
import os
from pathlib import Path
from config.settings import get_settings
from core.state import AgentState


# ── Dangerous patterns ───────────────────────────────────────────────────────

DANGEROUS_PATTERNS = [
    r"\bsudo\b",
    r"\brm\s+(-[a-zA-Z]*f|-[a-zA-Z]*r|--force|--recursive)",
    r"\brm\s+-rf\b",
    r"\bchmod\s+777\b",
    r"\bchmod\s+-R\b",
    r"\bchown\b",
    r"\bmkfs\b",
    r"\bdd\s+if=",
    r"\b(shutdown|reboot|poweroff|halt)\b",
    r"\b:\(\)\s*\{\s*:\|\:\s*&\s*\}\s*;",  # fork bomb
    r">\s*/dev/sd[a-z]",
    r">\s*/etc/",
    r">\s*/boot/",
    r">\s*/sys/",
    r">\s*/proc/",
    r"\bcurl\b.*\|\s*(bash|sh|zsh)",         # pipe to shell
    r"\bwget\b.*\|\s*(bash|sh|zsh)",
    r"\beval\b",
    r"\bexec\b",
    r"[;&|]\s*rm\b",
    r"\bnc\s+-[a-zA-Z]*l",                   # netcat listen
    r"\biptables\b",
    r"\bsystemctl\b",
]

MEDIUM_PATTERNS = [
    r"\bsudo\s+apt\b",
    r"\bsudo\s+pip\b",
    r"\bpip\s+install\b",
    r"\bnpm\s+install\s+-g\b",
    r"\brm\s+",                               # any rm (non-forced)
    r"\bmv\s+",                               # move can overwrite
    r"\bkill\b",
    r"\bpkill\b",
    r"\bgit\s+push\b",
    r"\bgit\s+reset\s+--hard\b",
    r"\bchmod\b",
    r"\bcrontab\b",
]

# System paths that should never be modified
RESTRICTED_PATHS = [
    "/etc", "/boot", "/sys", "/proc", "/dev",
    "/usr/bin", "/usr/sbin", "/sbin", "/bin",
    "/var/log", "/root",
]


class SafetyPolicy:
    """
    Validates and classifies shell commands before execution.
    
    Enforces:
        1. Risk classification (safe/medium/dangerous)
        2. Workspace restriction — blocks commands targeting system paths
        3. Command validation — rejects empty or obviously malformed commands
    """

    def __init__(self):
        self._settings = get_settings()
        # Initialize an independent state reader so the gateway knows current mode
        self._state = AgentState()

    def classify_risk(self, command: str) -> str:
        """
        Classify a command's risk level.
        
        Returns: "safe", "medium", or "dangerous"
        """
        command_lower = command.strip().lower()

        # Check dangerous patterns first
        for pattern in DANGEROUS_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                return "dangerous"

        # Check medium risk patterns
        for pattern in MEDIUM_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                return "medium"

        return "safe"

    def validate_command(self, command: str) -> dict:
        """
        Full validation pipeline for a command.
        
        Returns:
            dict with:
                - allowed: bool
                - risk: str (safe/medium/dangerous)
                - reason: str (explanation if blocked)
                - requires_confirmation: bool
        """
        command = command.strip()

        # Empty command
        if not command:
            return {
                "allowed": False,
                "risk": "safe",
                "reason": "Empty command.",
                "requires_confirmation": False,
            }
            
        # Hard length cap to prevent obfuscated payload injections
        if len(command) > 300:
             return {
                "allowed": False,
                "risk": "dangerous",
                "reason": "Command exceeds maximum safe length limit (300 chars).",
                "requires_confirmation": False,
            }

        # Classify risk
        risk = self.classify_risk(command)

        # Check workspace restriction
        workspace_violation = self._check_workspace_restriction(command)
        if workspace_violation and self._state.mode != "build":
            # BUILD mode turns workspace violations into warnings rather than hard blocks
            return {
                "allowed": False,
                "risk": "dangerous",
                "reason": workspace_violation,
                "requires_confirmation": False,
            }
            
        traversal_violation = self._check_path_traversal(command)
        if traversal_violation and self._state.mode != "build":
             return {
                "allowed": False,
                "risk": "dangerous",
                "reason": traversal_violation,
                "requires_confirmation": False,
            }

        # Determine behavior based on risk + operational mode
        # mode: "safe", "auto", "build"
        current_mode = self._state.mode
        
        if risk == "dangerous":
            if current_mode == "build" and workspace_violation:
                 risk_str = f"Dangerous command in BUILD mode hitting violation: {workspace_violation}"
            else:
                 risk_str = "Dangerous command detected."
                 
            return {
                "allowed": True,
                "risk": risk,
                "reason": f"{risk_str} Requires user confirmation.",
                "requires_confirmation": True, # Dangerous ALWAYS requires confirmation in all modes for MVP
            }
            
        elif risk == "medium":
            req_confirm = True # Default safe
            if current_mode in ("auto", "build"):
                req_confirm = False # Medium slides through under Auto or Build
                
            return {
                "allowed": True,
                "risk": risk,
                "reason": "Medium-risk command. Proceeding with caution.",
                "requires_confirmation": req_confirm,
            }
            
        else:
            return {
                "allowed": True,
                "risk": risk,
                "reason": "Command appears safe.",
                "requires_confirmation": False,
            }

    def _check_workspace_restriction(self, command: str) -> str | None:
        """
        Check if a command targets restricted system paths.
        
        Returns None if OK, or a reason string if blocked.
        """
        for path in RESTRICTED_PATHS:
            # Check for direct path references in the command
            if path in command and not command.strip().startswith(("cat ", "ls ", "head ", "tail ", "less ", "file ")):
                return (
                    f"Command targets restricted system path: {path}. "
                    f"This is blocked by workspace restriction policy."
                )
        return None
        
    def _check_path_traversal(self, command: str) -> str | None:
        """
        Prevents breaking out of the designated execution workspace using ../ arrays 
        while allowing local relative traversing (like ./ or child/../child) loosely.
        """
        # A simple heuristic: if a command attempts multiple sequential directory ascending
        # actions we raise a flag, heavily restricted in SAFE mode.
        if "../.." in command.replace(" ", ""):
            return "Command attempts excessive backwards path traversal (../..). Workspace boundary violation."
        return None

    def get_risk_display(self, risk: str) -> tuple[str, str]:
        """Return (emoji, color) for a risk level."""
        return {
            "safe": ("✓", "green"),
            "medium": ("⚠", "yellow"),
            "dangerous": ("⛔", "red"),
        }.get(risk, ("?", "white"))
