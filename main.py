"""
main.py — Friday CLI entry point.

Interactive loop with Rich styling, builtins, and optional verbose diagnostics.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

from rich.panel import Panel

from core.agent import FridayAgent
from core.ui import BANNER, PROMPT, SUBTITLE, console, status_line

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "session.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-20s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.FileHandler(LOG_FILE, mode="a")],
)

logger = logging.getLogger("friday.main")

BUILTIN_COMMANDS = {
    "exit": "Leave Friday",
    "quit": "Leave Friday",
    "status": "Show agent state",
    "skills": "List skills",
    "memory": "Memory stats",
    "safe": "Toggle safe mode",
    "clear": "Clear the screen",
    "help": "Built-in commands",
    "reload": "Reload skills from disk",
}


def handle_builtin(command: str, agent: FridayAgent) -> bool:
    cmd = command.strip().lower()

    if cmd in ("exit", "quit"):
        console.print("\n[friday.accent]Bye for now.[/friday.accent]\n")
        logger.info("Session ended by user")
        sys.exit(0)

    if cmd == "status":
        state = agent.state.to_dict()
        lines = [f"[friday.accent]{k}[/friday.accent] {v}" for k, v in state.items()]
        console.print(Panel("\n".join(lines), title="Status", border_style="friday.info", padding=(0, 1)))
        return True

    if cmd == "skills":
        from skills.loader import load_skills

        skills = load_skills()
        if skills:
            for s in skills:
                mark = "✓" if s.has_runner else "·"
                style = "friday.ok" if s.has_runner else "friday.dim"
                console.print(f"  [{style}]{mark}[/{style}] [bold]{s.name}[/bold] — {s.description[:72]}")
        else:
            console.print("  [friday.dim]No skills in skills/ yet.[/friday.dim]")
        return True

    if cmd == "memory":
        console.print(f"  [friday.dim]Session lines:[/friday.dim] {agent.session.size}")
        console.print(f"  [friday.dim]Long-term:[/friday.dim] {agent.mempalace.count}")
        return True

    if cmd == "safe":
        agent.state.safe_mode = not agent.state.safe_mode
        on = agent.state.safe_mode
        st = "friday.ok" if on else "friday.err"
        lab = "ON" if on else "OFF"
        console.print(f"  Safe mode: [{st}]{lab}[/{st}]")
        return True

    if cmd == "clear":
        console.clear()
        return True

    if cmd == "help":
        console.print()
        for name, desc in BUILTIN_COMMANDS.items():
            console.print(f"  [friday.accent]{name:8}[/friday.accent] {desc}")
        console.print()
        return True

    if cmd == "reload":
        n = agent.reload_skills()
        console.print(f"  [friday.ok]Reloaded {n} skill(s).[/friday.ok]")
        return True

    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Friday — local CLI copilot")
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show intent, plans, and per-step diagnostics in the terminal",
    )
    args = parser.parse_args()

    console.print(BANNER)
    console.print(f"  {SUBTITLE}\n")

    try:
        from core.scheduler import TaskScheduler

        agent = FridayAgent(verbose=args.verbose)
        scheduler = TaskScheduler(agent)

        from config.settings import get_settings
        from skills.loader import load_skills

        settings = get_settings()
        mr = settings.model_router
        status_line("Ready", "Friday is here", ok=True)
        status_line("Models", f"{mr.fast_model} · {mr.strong_model} · {mr.reason_model}", ok=True)
        status_line("Skills", f"{len(load_skills())} loaded", ok=True)
        status_line("Memory", f"{agent.mempalace.count} saved notes", ok=True)
        status_line("Safe mode", "ON" if agent.state.safe_mode else "OFF", ok=agent.state.safe_mode)
        if args.verbose:
            status_line("Verbose", "diagnostics on", ok=True)
        console.print()

    except Exception as e:
        console.print(f"\n[friday.err]Could not start:[/friday.err] {e}\n")
        logger.error("Init failed: %s", e, exc_info=True)
        sys.exit(1)

    logger.info("Session started at %s", datetime.now().isoformat())

    while True:
        try:
            scheduler.tick()
            for event in scheduler.pop_events():
                if event["type"] == "task_completed":
                    console.print(f"  [friday.dim]Background done:[/friday.dim] {event.get('task_id')}")
                elif event["type"] == "task_failed":
                    console.print(f"  [friday.warn]Background issue:[/friday.warn] {event.get('task_id')}")

            user_input = console.input(PROMPT).strip()
            if not user_input:
                continue

            if handle_builtin(user_input, agent):
                continue

            logger.info("Processing: %s", user_input)
            agent.process(user_input)

        except KeyboardInterrupt:
            console.print("\n[friday.dim]Ctrl+C — type exit to leave.[/friday.dim]")
            continue
        except EOFError:
            console.print("\n[friday.accent]Later.[/friday.accent]\n")
            break
        except Exception as e:
            console.print(f"\n[friday.err]{e}[/friday.err]\n")
            logger.error("Loop error: %s", e, exc_info=True)


if __name__ == "__main__":
    main()
