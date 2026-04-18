"""
skills/executor.py — Execute a matched skill's run.sh script.

Handles argument passing, working directory setup, and output capture.
Integrates with the safety policy for validation.
"""

import os
import shlex
import subprocess
from pathlib import Path

from skills.loader import Skill
from safety.policy import SafetyPolicy
from core.ui import console
policy = SafetyPolicy()


def execute_skill(skill: Skill, args: list[str] | None = None, cwd: str | None = None) -> dict:
    """
    Execute a skill's run.sh script.
    
    Args:
        skill: The Skill object to execute.
        args: Optional arguments to pass to the script.
        cwd: Working directory override.
    
    Returns:
        dict with stdout, stderr, exit_code, executed, skill_name.
    """
    if not skill.has_runner:
        return {
            "stdout": "",
            "stderr": f"Skill '{skill.name}' has no run.sh script.",
            "exit_code": -1,
            "executed": False,
            "skill_name": skill.name,
        }

    run_sh = skill.path / "run.sh"

    # Ensure the script is executable
    if not os.access(run_sh, os.X_OK):
        try:
            os.chmod(run_sh, 0o755)
        except OSError:
            pass

    # Build command
    cmd_parts = [str(run_sh)]
    if args:
        cmd_parts.extend(args)

    command_str = shlex.join(cmd_parts)

    # Validate through safety policy
    validation = policy.validate_command(command_str)
    if not validation["allowed"]:
        return {
            "stdout": "",
            "stderr": f"Skill blocked by safety policy: {validation['reason']}",
            "exit_code": -1,
            "executed": False,
            "skill_name": skill.name,
        }

    # Confirmation for risky skills
    if validation["requires_confirmation"]:
        risk = validation["risk"]
        _, color = policy.get_risk_display(risk)
        console.print(f"  [{color}]{risk}[/] skill [bold]{skill.name}[/bold]")
        try:
            confirm = console.input("[friday.warn]  ok? (y/n): [/friday.warn]").strip().lower()
        except (EOFError, KeyboardInterrupt):
            confirm = "n"

        if confirm not in ("y", "yes"):
            return {
                "stdout": "",
                "stderr": "Skill execution cancelled by user.",
                "exit_code": -1,
                "executed": False,
                "skill_name": skill.name,
            }

    # Execute
    work_dir = cwd or os.getcwd()

    import time
    from skills.loader import save_skill_metrics
    
    start_time = time.time()
    try:
        result = subprocess.run(
            cmd_parts,
            cwd=work_dir,
            capture_output=True,
            text=True,
            timeout=120,
            env={**os.environ, "FRIDAY_SKILL": skill.name},
        )
        
        duration = time.time() - start_time
        
        # Update metrics
        skill.usage_count += 1
        
        # Incremental moving average for runtime
        if skill.usage_count == 1:
            skill.avg_runtime = duration
        else:
            skill.avg_runtime = ((skill.avg_runtime * (skill.usage_count - 1)) + duration) / skill.usage_count
            
        # Update success rate (exit code 0 = success)
        is_success = 1.0 if result.returncode == 0 else 0.0
        if skill.usage_count == 1:
            skill.success_rate = is_success
        else:
            skill.success_rate = ((skill.success_rate * (skill.usage_count - 1)) + is_success) / skill.usage_count
            
        # Persist metrics back to skill.md
        save_skill_metrics(skill)

        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode,
            "executed": True,
            "skill_name": skill.name,
        }

    except subprocess.TimeoutExpired:
        return {
            "stdout": "",
            "stderr": f"Skill '{skill.name}' timed out after 120 seconds.",
            "exit_code": -1,
            "executed": False,
            "skill_name": skill.name,
        }
    except Exception as e:
        return {
            "stdout": "",
            "stderr": f"Skill execution error: {e}",
            "exit_code": -1,
            "executed": False,
            "skill_name": skill.name,
        }
