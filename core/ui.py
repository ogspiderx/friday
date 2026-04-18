"""
Shared Rich console, theme, and static UI strings for Friday.
"""

from rich.console import Console
from rich.theme import Theme
from rich.panel import Panel
from rich import box

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

BANNER = "[friday.accent]Friday[/friday.accent] — local copilot"

SUBTITLE = "[friday.dim]skills · memory · shell · [bold]help[/bold] · [bold]exit[/bold][/friday.dim]"

PROMPT = "[friday.accent]Friday ›[/friday.accent] "


def status_line(label: str, value: str, *, ok: bool = True) -> None:
    style = "friday.ok" if ok else "friday.dim"
    console.print(f"  [{style}]–[/{style}] {label}  {value}")


def panel_user_message(title: str, body: str, style: str = "friday.accent") -> None:
    console.print(Panel(body.strip(), title=title, border_style=style, box=box.MINIMAL, padding=(0, 1)))
