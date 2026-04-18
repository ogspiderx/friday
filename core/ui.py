"""
Shared Rich console, theme, and static UI strings for Friday.

One console instance keeps colors and typography consistent app-wide.
"""

from rich.console import Console
from rich.theme import Theme
from rich.panel import Panel
from rich import box

# Muted violet / rose palette on dark terminals
FRIDAY_THEME = Theme(
    {
        "friday.accent": "bold #c4a7e7",
        "friday.dim": "dim #908caa",
        "friday.ok": "#a6e3a1",
        "friday.warn": "#f9e2af",
        "friday.err": "#f38ba8",
        "friday.info": "#89b4fa",
        "repr.str": "#f5c2e7",
    }
)

console = Console(theme=FRIDAY_THEME, highlight=False, soft_wrap=True)

BANNER = """[friday.accent]
    ╭──────────────────────────────────────────╮
    │                                          │
    │     ✦  [bold]Friday[/bold]  — local copilot  ✦      │
    │                                          │
    ╰──────────────────────────────────────────╯
[/friday.accent]"""

SUBTITLE = "[friday.dim]Skills · memory · careful shell · type [bold]help[/bold] · [bold]exit[/bold] quits[/friday.dim]"

PROMPT = "[friday.accent]Friday ›[/friday.accent] "


def status_line(label: str, value: str, *, ok: bool = True) -> None:
    sym = "✓" if ok else "·"
    style = "friday.ok" if ok else "friday.dim"
    console.print(f"  [{style}]{sym}[/{style}] {label} [friday.dim]{value}[/friday.dim]")


def panel_user_message(title: str, body: str, style: str = "friday.accent") -> None:
    console.print(Panel(body.strip(), title=title, border_style=style, box=box.ROUNDED, padding=(0, 1)))
