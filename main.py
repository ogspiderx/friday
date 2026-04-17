"""
main.py — FRIDAY CLI entry point.

Provides the interactive terminal loop with rich formatting,
command history, and graceful lifecycle management.
"""

import sys
import logging
from pathlib import Path
from datetime import datetime

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich import box

# ── Setup logging before anything else ────────────────────────────────────────
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "session.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-20s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, mode="a"),
    ],
)

logger = logging.getLogger("friday.main")

# ── Imports (after logging setup) ─────────────────────────────────────────────
from core.agent import FridayAgent
from config.settings import get_settings

console = Console()


# ── Banner ────────────────────────────────────────────────────────────────────

BANNER = """[bold cyan]
 ███████╗██████╗ ██╗██████╗  █████╗ ██╗   ██╗
 ██╔════╝██╔══██╗██║██╔══██╗██╔══██╗╚██╗ ██╔╝
 █████╗  ██████╔╝██║██║  ██║███████║ ╚████╔╝ 
 ██╔══╝  ██╔══██╗██║██║  ██║██╔══██║  ╚██╔╝  
 ██║     ██║  ██║██║██████╔╝██║  ██║   ██║   
 ╚═╝     ╚═╝  ╚═╝╚═╝╚═════╝ ╚═╝  ╚═╝   ╚═╝   
[/bold cyan]"""

SUBTITLE = "[dim]Local-first AI agent · Skills · Memory · Safe Shell[/dim]"


# ── Built-in commands ─────────────────────────────────────────────────────────

BUILTIN_COMMANDS = {
    "exit":     "Exit FRIDAY",
    "quit":     "Exit FRIDAY",
    "status":   "Show agent state",
    "skills":   "List available skills",
    "memory":   "Show memory stats",
    "safe":     "Toggle safe mode",
    "clear":    "Clear screen",
    "help":     "Show available commands",
    "reload":   "Reload skills from disk",
}


def handle_builtin(command: str, agent: FridayAgent) -> bool:
    """
    Handle built-in CLI commands.
    
    Returns True if the command was handled, False otherwise.
    """
    cmd = command.strip().lower()

    if cmd in ("exit", "quit"):
        console.print("\n[bold cyan]  See you later. 🤙[/bold cyan]\n")
        logger.info("Session ended by user")
        sys.exit(0)

    if cmd == "status":
        state = agent.state.to_dict()
        lines = []
        for k, v in state.items():
            lines.append(f"  [cyan]{k}[/cyan]: {v}")
        console.print(Panel("\n".join(lines), title="📊 Agent State", border_style="cyan"))
        return True

    if cmd == "skills":
        from skills.loader import load_skills
        skills = load_skills()
        if skills:
            for s in skills:
                status = "✓" if s.has_runner else "✗"
                console.print(f"  [{('green' if s.has_runner else 'red')}]{status}[/] [bold]{s.name}[/bold] — {s.description[:60]}")
                if s.triggers:
                    console.print(f"    [dim]triggers: {', '.join(s.triggers)}[/dim]")
        else:
            console.print("  [dim]No skills found. Add skills to the skills/ directory.[/dim]")
        return True

    if cmd == "memory":
        console.print(f"  [cyan]Session entries:[/cyan] {agent.session.size}")
        console.print(f"  [cyan]Long-term memories:[/cyan] {agent.mempalace.count}")
        return True

    if cmd == "safe":
        agent.state.safe_mode = not agent.state.safe_mode
        status = "ON" if agent.state.safe_mode else "OFF"
        color = "green" if agent.state.safe_mode else "red"
        console.print(f"  Safe mode: [{color}]{status}[/{color}]")
        return True

    if cmd == "clear":
        console.clear()
        return True

    if cmd == "help":
        console.print()
        for cmd_name, desc in BUILTIN_COMMANDS.items():
            console.print(f"  [bold cyan]{cmd_name:10}[/bold cyan] {desc}")
        console.print()
        return True

    if cmd == "reload":
        count = agent.reload_skills()
        console.print(f"  [green]Reloaded {count} skill(s)[/green]")
        return True

    return False


# ── Main loop ─────────────────────────────────────────────────────────────────

def main():
    """Main entry point for FRIDAY."""
    console.print(BANNER)
    console.print(f"  {SUBTITLE}")
    console.print(f"  [dim]Type [bold]help[/bold] for commands · [bold]exit[/bold] to quit[/dim]\n")

    try:
        agent = FridayAgent()
        from core.scheduler import TaskScheduler
        scheduler = TaskScheduler(agent)
        
        settings = get_settings()
        console.print(f"  [green]✓[/green] Agent ready")
        console.print(f"  [green]✓[/green] Models: [dim]fast={settings.model_router.fast_model} · strong={settings.model_router.strong_model}[/dim]")
        
        from skills.loader import load_skills
        skill_count = len(load_skills())
        console.print(f"  [green]✓[/green] Skills: {skill_count} loaded")
        console.print(f"  [green]✓[/green] Memory: {agent.mempalace.count} long-term entries")
        console.print(f"  [green]✓[/green] Safe mode: {'ON' if agent.state.safe_mode else 'OFF'}")
        console.print()

    except Exception as e:
        console.print(f"\n  [bold red]✗ Failed to initialize:[/bold red] {e}")
        logger.error(f"Init failed: {e}", exc_info=True)
        sys.exit(1)

    logger.info(f"Session started at {datetime.now().isoformat()}")

    # Interactive loop
    while True:
        try:
            # Phase 15: Scheduler Tick
            scheduler.tick()
            events = scheduler.pop_events()
            for event in events:
                if event["type"] == "task_completed":
                    console.print(f"  [dim]🔔 Background Task Completed:[/dim] [green]{event.get('task_id')}[/green]")
                elif event["type"] == "task_failed":
                    console.print(f"  [dim]🔔 Background Task Failed:[/dim] [red]{event.get('task_id')}[/red]")
                    
            user_input = console.input("[bold cyan]friday >[/bold cyan] ").strip()

            if not user_input:
                continue

            # Check built-in commands first
            if handle_builtin(user_input, agent):
                continue

            # Process through the agent pipeline
            logger.info(f"Processing: {user_input}")
            agent.process(user_input)

        except KeyboardInterrupt:
            console.print("\n[dim]  Ctrl+C — type 'exit' to quit[/dim]")
            continue

        except EOFError:
            console.print("\n[bold cyan]  See you later. 🤙[/bold cyan]\n")
            break

        except Exception as e:
            console.print(f"\n  [red]Error: {e}[/red]")
            logger.error(f"Unhandled error: {e}", exc_info=True)
            continue


if __name__ == "__main__":
    main()
