"""
core/scheduler.py

Active Task Runner. Executes pending tasks silently in the background
or interleaved with the CLI loop. Emits structured events rather than
polluting stdout.
"""

from core.tasks import TaskManager
from core.agent import FridayAgent
import logging
from typing import List, Dict

logger = logging.getLogger("friday.scheduler")

class TaskScheduler:
    def __init__(self, agent: FridayAgent):
        self.task_manager = TaskManager()
        self.agent = agent
        self.event_queue: List[Dict] = []
        
        # Phase 19: Crash Recovery
        self.task_manager.release_stale_locks(timeout_seconds=300)
        
    def add_task(self, goal: str) -> str:
        """Adds a task to the queue."""
        task = self.task_manager.add_task(goal)
        self.event_queue.append({
            "type": "task_added",
            "task_id": task.id,
            "goal": task.goal
        })
        return task.id

    def tick(self):
        """
        Executes one step of the first pending task it finds.
        Designed to be called between interactive shell prompts.
        """
        pending = self.task_manager.get_pending()
        if not pending:
            return
            
        task = pending[0]
        
        # Suppress printing via stdout monkey-patching or silent config in a real env,
        # but since FRIDAY binds heavily to `rich.console`, we use a dedicated silent execute.
        # To avoid duplicating the entire agent process loop, we will use the agent's process 
        # but intercept its console prints. For simplicity in this demo, we run the agent process
        # and capture the standard log.
        
        # Ideally, we should add `silent=True` to Agent.process. For now, we will just 
        # log what task we are attacking.
        logger.info(f"Scheduler ticketing task: {task.id} -> {task.goal}")
        
        self.event_queue.append({
            "type": "task_start",
            "task_id": task.id,
            "goal": task.goal
        })
        
        # Acquire execution lock
        self.task_manager.lock(task.id)
        
        try:
            # We treat the task goal as native input to the processing engine.
            # State tracks commands.
            response = self.agent.process(task.goal)
            
            # If we didn't exception out, consider it a single pass completion.
            # Long-running tasks might need sub-stepping, but Phase 15 MVP clears it on success.
            self.task_manager.complete(task.id)
            
            self.event_queue.append({
                "type": "task_completed",
                "task_id": task.id,
                "summary": response[:100]
            })
            logger.info(f"Task {task.id} completed silently.")
            
        except Exception as e:
            self.task_manager.fail(task.id)
            self.event_queue.append({
                "type": "task_failed",
                "task_id": task.id,
                "error": str(e)
            })
            logger.error(f"Task {task.id} failed: {e}")

    def pop_events(self) -> List[Dict]:
        """Returns all unread UI events to be gracefully displayed by the foreground."""
        events = self.event_queue.copy()
        self.event_queue.clear()
        return events
