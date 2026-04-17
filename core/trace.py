"""
core/trace.py

Trace Inspector. Captures the total lifecycle of an execution frame, 
providing granular deterministic inspectability into every 
turn of the loop.
"""

import json
import uuid
import os
from datetime import datetime
from pathlib import Path
from config.settings import get_settings

class TraceContext:
    def __init__(self):
        settings = get_settings()
        self.traces_dir = settings.project_root / "logs" / "traces"
        os.makedirs(self.traces_dir, exist_ok=True)
        self.clear()
        
    def clear(self):
        """Reset the payload for a new process tick."""
        self.payload = {
            "trace_id": str(uuid.uuid4()),
            "timestamp": datetime.now().isoformat(),
            "input": "",
            "intent": {},
            "retrieved_memories": [],
            "matched_skills": [],
            "plan": {},
            "commands": [],
            "executions": [],
            "evaluations": [],
            "skill_generation": None
        }
        
    def set_input(self, text: str):
        self.payload["input"] = text
        
    def set_intent(self, intent_dict: dict):
        self.payload["intent"] = intent_dict
        
    def add_memories(self, memories: list):
        self.payload["retrieved_memories"].extend(memories)
        
    def add_skills(self, skills: list):
        self.payload["matched_skills"].extend(skills)
        
    def set_plan(self, plan_dict: dict):
        self.payload["plan"] = plan_dict
        
    def add_command(self, cmd_repr: str):
        self.payload["commands"].append(cmd_repr)
        
    def add_execution(self, executed_dict: dict):
        self.payload["executions"].append(executed_dict)
        
    def add_evaluation(self, eval_dict: dict):
        self.payload["evaluations"].append(eval_dict)
        
    def set_skill_generation(self, success: bool, reason: str = ""):
        self.payload["skill_generation"] = {"success": success, "reason": reason}
        
    def commit(self):
        """Flushes the trace to disk."""
        if not self.payload["input"]:
             return # Ignore empty ticks
             
        trace_file = self.traces_dir / f"run-{self.payload['trace_id']}.json"
        try:
            with open(trace_file, "w") as f:
                json.dump(self.payload, f, indent=2)
        except Exception:
            pass

# Process-level singleton interceptor
_trace_ctx = TraceContext()

def get_trace() -> TraceContext:
    return _trace_ctx
