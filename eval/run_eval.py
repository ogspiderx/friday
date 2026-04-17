"""
eval/run_eval.py

Runs the empirical evaluation suite against the active FRIDAY agent.
Loads scenarios.json, executes them using the pipeline, and verifies 
if the agent's behavior matched expectations via the extracted Trace.
"""

import json
import sys
import os
from pathlib import Path

# Adjust path to enable importing core modules from the project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.agent import FridayAgent
from tests.harness import attach_harness
from rich.console import Console

console = Console()
SCENARIOS_PATH = Path(__file__).parent / "scenarios.json"
TRACES_PATH = Path(__file__).parent.parent / "logs" / "traces"

def load_scenarios():
    with open(SCENARIOS_PATH, "r") as f:
        return json.load(f)

def run_suite():
    console.print("[bold cyan]Starting Evaluation Suite...[/bold cyan]")
    
    agent = FridayAgent()
    # Mock network bounds so eval is deterministic and avoids API costs
    # In a real enterprise CI, you'd toggle this depending on live vs local mode.
    harness = attach_harness(agent, scenario_name="eval_suite")
    scenarios = load_scenarios()
    
    results = {
        "passed": 0,
        "failed": 0,
        "total": len(scenarios)
    }

    for scenario in scenarios:
        console.print(f"\n[bold yellow]Evaluating scenario:[/bold yellow] {scenario['id']}")
        
        # Suppress input prompts physically blocking the eval
        # In a real environment we would mock console.input, but we'll 
        # just run through the pipeline
        agent.process(scenario["prompt"])
        
        # Pull the latest trace file deterministically via timestamps or assuming the 
        # last created file in TRACES_PATH is ours
        trace_files = sorted(TRACES_PATH.glob("run-*.json"), key=os.path.getmtime)
        if not trace_files:
            console.print("[red]No trace found for execution![/red]")
            results["failed"] += 1
            continue
            
        latest_trace = trace_files[-1]
        with open(latest_trace, "r") as f:
            trace_data = json.load(f)
            
        # Assertion Checking
        intent = trace_data.get("intent", {}).get("intent", "unknown")
        
        passed = True
        
        # Asser Intent
        if intent != scenario["expected_intent"]:
            console.print(f"  [red]✗ Intent mismatch.[/red] Expected {scenario['expected_intent']}, got {intent}")
            passed = False
        else:
            console.print(f"  [green]✓[/green] Intent matched: {intent}")
            
        # Due to harness mock restrictions, deeper execution checks (secure block states)
        # require full live-LLM evaluation suites. For now, we tally.
        if passed:
            results["passed"] += 1
        else:
            results["failed"] += 1
            
    console.print("\n[bold cyan]Evaluation Summary:[/bold cyan]")
    console.print(f"  Total: {results['total']}")
    console.print(f"  Passed: [green]{results['passed']}[/green]")
    console.print(f"  Failed: [red]{results['failed']}[/red]")

if __name__ == "__main__":
    run_suite()
