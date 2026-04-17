"""
core/reflection.py — The Reflection Pipeline.

Analyzes the most recent interaction loops in session memory.
If it detects inefficiencies (>2 steps to achieve a goal) or
failure-then-correction loops, it packages the scenario and 
triggers the SkillGenerator to permanently learn the behavior.
"""

from memory.session import SessionMemory, MemoryEntry
from skills.generator import SkillGenerator
from config.settings import get_settings
import logging

logger = logging.getLogger("friday.reflection")

class ReflectionEngine:
    """
    Evaluates recent operations. If a task took multiple commands
    or failed and required user overriding, it extracts the objective 
    and the final working command list, sending them to the Generator.
    """
    def __init__(self):
        self.generator = SkillGenerator()
        self._settings = get_settings()

    def analyze_turn(self, session: SessionMemory):
        """
        Scan session memory for learning opportunities.
        Since analyzing every turn could be expensive, we only look for heuristic markers:
        - "user" requests a task
        - "assistant" executes shell commands
        - the sequence of shell commands > 2
        """
        # Get the last 10 entries
        recent = session.get_recent(10)
        
        # We need a user request followed by multiple successful shell executions
        # For simplicity in this iteration: if the agent executed a long plan, 
        # let's consolidate it.
        
        # We look for the last 'user' intent that was 'shell_task'.
        user_reqs = [e for e in recent if e.role == "user"]
        if not user_reqs: return
        
        last_request = user_reqs[-1]
        
        # We scan the metadata of the assistant responses that followed 
        # this user request. In core/agent.py we will attach 'commands_executed' to metadata
        # of the assistant's memory entry.
        
        # Find the assistant response matching the last user request (based on time ordering)
        # We assume the most recent 'assistant' entry belongs to the most recent 'user' entry.
        assistant_resps = [e for e in recent if e.role == "assistant"]
        if not assistant_resps: return
        
        last_response = assistant_resps[-1]
        
        commands_run = last_response.metadata.get("commands_executed", [])
        
        # Threshold: if it took 2 or more commands to achieve something, learn it as a skill.
        if len(commands_run) >= 2:
            logger.info("Reflection Engine triggered: Multi-step shell task detected.")
            # Trigger Skill Generator.
            self.generator.create_skill(last_request.content, commands_run)
            # Remove from metadata so we don't trigger again on the next turn unnecessarily
            last_response.metadata["commands_executed"] = []
