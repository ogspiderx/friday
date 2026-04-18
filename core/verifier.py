"""
core/verifier.py

Deterministic verification layer replacing raw LLM guessing where possible.
Analyzes the structured command that was emitted by the planner, and 
checks the resulting system state computationally.
"""

import os
import shutil
import subprocess
from pathlib import Path

class DeterministicVerifier:
    def verify(self, command_spec: dict, execution_result: dict, default_cwd: str = None) -> dict:
        """
        Runs deterministic checks based on the structured command provided.
        Returns: { "success": bool, "reason": str, "confidence": float (0-1) }
        """
        # If execution fundamentally blew up or timed out, it's a failure.
        if not execution_result.get("executed"):
            return {
                "success": False,
                "reason": f"Execution engine aborted: {execution_result.get('stderr', '')}",
                "confidence": 1.0
            }
            
        cmd_type = command_spec.get("type", "")
        action = command_spec.get("action", "")
        params = command_spec.get("params", {})
        exit_code = execution_result.get("exit_code", -1)
        
        work_dir = Path(default_cwd or os.getcwd()).resolve()

        # --- 1 & 2. Filesystem & Directories ---
        if cmd_type == "filesystem":
            path_str = params.get("path")
            if not path_str:
                return {"success": False, "reason": "No path provided in filesystem action", "confidence": 0.9}

            target = (work_dir / path_str).resolve()
            try:
                target.relative_to(work_dir)
            except ValueError:
                return {"success": False, "reason": "Path outside workspace", "confidence": 1.0}
            
            if action in ("create_directory", "create_file"):
                if target.exists():
                    return {"success": True, "reason": f"Target successfully created at {target}", "confidence": 1.0}
                else:
                    return {"success": False, "reason": f"Expected target to exist, but missing: {target}", "confidence": 1.0}
                    
            elif action == "delete":
                if not target.exists():
                    return {"success": True, "reason": f"Target does not exist (delete successful): {target}", "confidence": 1.0}
                else:
                    return {"success": False, "reason": f"Target still exists after delete action: {target}", "confidence": 1.0}
                    
            elif action == "read_file":
                # If we read it, check if stdout actually has content
                if exit_code == 0 and execution_result.get("stdout"):
                    return {"success": True, "reason": "File read successfully.", "confidence": 0.9}
                else:
                    return {"success": False, "reason": "File read yielded no content or failed.", "confidence": 0.8}

        elif cmd_type == "persona":
            if exit_code == 0 and "error" not in execution_result.get("stderr", "").lower():
                return {"success": True, "reason": "Persona file updated.", "confidence": 0.95}
            return {"success": False, "reason": execution_result.get("stderr", "persona update failed"), "confidence": 0.9}

        # --- 3. Git Operations ---
        elif cmd_type == "git":
            if action == "clone":
                # Assuming the last argument is the path or the repo name
                # Just check if exit code was 0 and some git folder exists inside CWD (approximation)
                if exit_code == 0:
                    return {"success": True, "reason": "Git clone exited cleanly.", "confidence": 0.7}
                    
            elif action == "status":
                if "fatal: not a git repository" in execution_result.get("stderr", "").lower():
                    return {"success": False, "reason": "Not a git repository.", "confidence": 1.0}
                if exit_code == 0:
                    return {"success": True, "reason": "Git status retrieved.", "confidence": 0.8}

        # --- 4. Package Managers / Installations ---
        elif cmd_type == "package":
            if action in ("install", "add"):
                # E.g., apt install vim. We can try to run `which vim` (or whatever the arg was)
                args = params.get("args", [])
                if args:
                    # Very naive: assume the first argument is the package name
                    package = args[0]
                    if shutil.which(package):
                        return {"success": True, "reason": f"Binary '{package}' is now available in PATH.", "confidence": 0.9}
                    else:
                        # Sometimes packages don't expose identical bin names, so lower confidence
                        return {"success": (exit_code == 0), "reason": f"Command exited with {exit_code}, but binary '{package}' not directly found in PATH.", "confidence": 0.6}
            
        # --- 5. Generic / System ops ---
        # Exit code 0 is NOT sufficient alone for 100% confidence, but it's a signal.
        if exit_code == 0:
            stdout_stripped = execution_result.get("stdout", "").strip()
            stderr_stripped = execution_result.get("stderr", "").strip()
            
            # Tools often write to stderr even on success, but if stdout is totally empty and stderr has error keywords:
            if not stdout_stripped and "error:" in stderr_stripped.lower():
                 return {"success": False, "reason": "Exit code 0 but stderr indicates failure.", "confidence": 0.8}
                 
            return {"success": True, "reason": "Command executed with exit code 0.", "confidence": 0.5} # Low confidence, Critic should take over
            
        # If none of the specific rules hit, but exit code is non-zero, it almost certainly failed
        return {
            "success": False, 
            "reason": f"Non-zero exit code ({exit_code}).", 
            "confidence": 0.8
        }
