from typing import Literal
from rich import print as rich_print

ActionColor = Literal["red", "green", "yellow", "blue", "magenta", "cyan", "white"]

_QUIET = False


def set_quiet(quiet: bool) -> None:
    """Set global quiet mode for logging."""
    global _QUIET
    _QUIET = quiet


def is_quiet() -> bool:
    """Check if quiet mode is enabled."""
    return _QUIET


def log_action(
    action_name: str,
    action_message: str,
    action_color: ActionColor = "white",
) -> None:
    """Print a formatted action log line if quiet mode is not enabled."""
    if _QUIET:
        return
    rich_print(
        f"[bold {action_color}]{action_name:>10}[/bold {action_color}]: {action_message}"
    )
