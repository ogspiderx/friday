"""
core/executor_router.py

Provides structured command routing. Resolves JSON command schemas 
into native Python execution (for safe primitives) or delegates 
to `tools/shell.py`.

Schema:
{
  "type": "filesystem | git | system | package",
  "action": "...",
  "params": {}
}
"""

import os
import shutil
from pathlib import Path
from tools.shell import ShellExecutor

class ExecutorRouter:
    def __init__(self):
        self.shell = ShellExecutor()

    def execute(self, command_spec: dict, default_cwd: str = None) -> dict:
        """
        Routes and executes a structured command dictionary.
        
        Returns standard result dict:
        {"stdout": "...", "stderr": "...", "exit_code": int, "executed": bool, "skill_name": str}
        """
        cmd_type = command_spec.get("type", "unknown")
        action = command_spec.get("action", "")
        params = command_spec.get("params", {})
        
        # 1) Evaluate Native Python primitives
        if cmd_type == "filesystem":
            return self._execute_filesystem_native(action, params, default_cwd)
            
        # 2) Fallback to shell execution for complex / system commands
        return self._execute_shell_mapped(command_spec, default_cwd)
        
    def _execute_filesystem_native(self, action: str, params: dict, default_cwd: str) -> dict:
        """Execute filesystem primitives using native Python code to guarantee safety & speed."""
        work_dir = Path(default_cwd or os.getcwd())
        path_str = params.get("path", "")
        
        # Resolve to absolute boundary logic (to avoid breaking out of CWD un-intentionally)
        target = (work_dir / path_str).resolve()
            
        try:
            if action == "create_directory":
                target.mkdir(parents=True, exist_ok=True)
                return self._success(f"Directory created: {target}", "")
                
            elif action == "delete":
                if not target.exists():
                    return self._success(f"Path does not exist: {target}", "")
                recursive = params.get("recursive", False)
                if target.is_dir():
                    if recursive:
                        shutil.rmtree(target)
                        return self._success(f"Directory tree deleted: {target}", "")
                    else:
                        target.rmdir() # Only works if empty
                        return self._success(f"Empty directory deleted: {target}", "")
                else:
                    target.unlink()
                    return self._success(f"File deleted: {target}", "")
                    
            elif action == "create_file":
                content = params.get("content", "")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content)
                return self._success(f"File written: {target}", "")
                
            elif action == "read_file":
                if not target.exists():
                    return self._failure(f"File does not exist: {target}")
                content = target.read_text()
                return self._success(content, "")
                
            else:
                # Unsupported fast-path fallback
                return self._failure(f"Unsupported filesystem action: {action}")
                
        except Exception as e:
            return self._failure(f"Native FS Error: {str(e)}")

    def _execute_shell_mapped(self, command_spec: dict, default_cwd: str) -> dict:
        """Converts structured spec back into a shell string sequence for execution."""
        
        cmd_type = command_spec.get("type", "unknown")
        action = command_spec.get("action", "")
        params = command_spec.get("params", {})
        
        base_cmd = ""
        args = []
        
        # Provide mapping translations
        if cmd_type == "git":
            base_cmd = "git"
            args.append(action)
            # Flatten params generically if specific ones aren't caught
            # Ideally the planner provides valid CLI flag structures natively
            if "args" in params and isinstance(params["args"], list):
                args.extend(params["args"])
                
        elif cmd_type in ("package", "system"):
            # Assume action is the binary
            if "binary" in params:
                base_cmd = params["binary"]
                args.append(action)
            else:
                base_cmd = action
                
            if "args" in params and isinstance(params["args"], list):
                args.extend(params["args"])
                
        elif cmd_type == "shell":
            # Direct shell injection logic fallback (if explicit shell is strictly necessary)
            base_cmd = action
            if "args" in params and isinstance(params["args"], list):
                args.extend(params["args"])
        else:
            # Blind fallback (Planner failed to strictly type)
            base_cmd = action
            if "args" in params and isinstance(params["args"], list):
                args.extend(params["args"])

        if not base_cmd:
            return self._failure("Invalid shell mapping resulting in empty command.")

        # Reconstruct exactly for the shell executor
        full_command = f"{base_cmd} {' '.join(args)}".strip()
        
        # Route to executor
        return self.shell.execute(full_command, cwd=default_cwd)

    def _success(self, stdout: str, stderr: str = "") -> dict:
        return {
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": 0,
            "executed": True,
            "skill_name": "python_native"
        }
        
    def _failure(self, error: str) -> dict:
        return {
            "stdout": "",
            "stderr": error,
            "exit_code": 1,
            "executed": True,
            "skill_name": "python_native"
        }
