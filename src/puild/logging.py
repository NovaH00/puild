from __future__ import annotations

import sys
from typing import Any, Literal
from rich import print as rich_print
from rich.markup import escape

ActionColor = Literal["red", "green", "yellow", "blue", "magenta", "cyan", "white"]

_QUIET = False
_DEFAULT_INDENT = "    "


def set_quiet(quiet: bool) -> None:
    """Set global quiet mode for logging."""
    global _QUIET
    _QUIET = quiet


def is_quiet() -> bool:
    """Check if quiet mode is enabled."""
    return _QUIET


def set_default_indent(indent: str) -> None:
    """Set global default indentation string for command outputs."""
    global _DEFAULT_INDENT
    _DEFAULT_INDENT = indent


def get_default_indent() -> str:
    """Get the global default indentation string."""
    return _DEFAULT_INDENT


def log_action(
    action_name: str,
    action_message: str,
    action_color: ActionColor = "white",
) -> None:
    """Print a formatted action log line if quiet mode is not enabled."""
    if _QUIET:
        return
    prefix = f"[bold {action_color}]{action_name:>10}[/bold {action_color}]: "
    lines = action_message.splitlines()
    if not lines:
        rich_print(prefix.rstrip())
        return

    rich_print(f"{prefix}{escape(lines[0])}")
    # Indent subsequent lines of a multiline action message to align after the prefix
    indent_pad = " " * 12
    for line in lines[1:]:
        rich_print(f"{indent_pad}{escape(line)}")


def log_indented(
    message: str,
    indent: str | None = None,
    stream: Any = sys.stdout,
) -> None:
    """Print multiline text with each line indented."""
    if _QUIET or not message:
        return
    eff_indent = _DEFAULT_INDENT if indent is None else indent
    for line in message.splitlines():
        if not line.strip():
            stream.write("\n")
        else:
            stream.write(f"{eff_indent}{line}\n")
    stream.flush()
