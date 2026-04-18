"""
core/context.py — Environment Awareness.

Dynamic generation of the system context: OS, active directory metrics, 
running processes, or language environment (e.g. package.json, requirements.txt).
"""

import os
import platform
import subprocess
from pathlib import Path
from datetime import datetime

class EnvironmentContext:
    @staticmethod
    def get_info() -> str:
        """Returns a formatted string describing the environment."""
        parts = []

        # Target time + environment info
        current_time = datetime.now().astimezone().strftime("%A, %Y-%m-%d %H:%M:%S %Z")
        parts.append(f"Current System Time: {current_time}")
        parts.append(f"OS: {platform.system()} {platform.release()} ({platform.machine()})")
        parts.append(f"CWD: {os.getcwd()}")

        # Check for Git
        if Path(".git").exists():
            try:
                branch = subprocess.check_output(
                    ["git", "branch", "--show-current"], 
                    stderr=subprocess.DEVNULL, 
                    text=True
                ).strip()
                parts.append(f"Git Repo: Active, branch: {branch}")
            except Exception:
                pass

        # Language environment markers
        markers = []
        if Path("package.json").exists(): markers.append("Node.js/NPM")
        if Path("requirements.txt").exists(): markers.append("Python (requirements.txt)")
        if Path("pyproject.toml").exists(): markers.append("Python (pyproject.toml)")
        if Path("Cargo.toml").exists(): markers.append("Rust")
        if Path("go.mod").exists(): markers.append("Go")
        
        if markers:
            parts.append(f"Environment Markers: {', '.join(markers)}")

        return "\n".join(parts)
