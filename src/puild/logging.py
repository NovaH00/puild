from __future__ import annotations

import contextlib
import logging
import re
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Literal

from rich import print as rich_print
from rich.markup import escape

ActionColor = Literal["red", "green", "yellow", "blue", "magenta", "cyan", "white"]

_QUIET = False
_DEFAULT_INDENT = "              "
_ANSI_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from text."""
    return _ANSI_RE.sub("", text)


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


class ConsoleActionHandler(logging.Handler):
    """Handler that formats action logs to the terminal using rich."""

    def emit(self, record: logging.LogRecord) -> None:
        if _QUIET:
            return
        try:
            action = getattr(record, "action", None)
            color = getattr(record, "color", "white")
            msg = record.getMessage()

            if action:
                prefix = f"[bold {color}]{action:>10}[/bold {color}]: "
                lines = msg.splitlines()
                if not lines:
                    rich_print(prefix.rstrip())
                    return
                rich_print(f"{prefix}{escape(lines[0])}")
                indent_pad = " " * 12
                for line in lines[1:]:
                    rich_print(f"{indent_pad}{escape(line)}")
            else:
                # Direct message or indented block
                if "\x1b" in msg:
                    sys.stdout.write(msg + "\n")
                    sys.stdout.flush()
                else:
                    for line in msg.splitlines():
                        if not line.strip():
                            sys.stdout.write("\n")
                        else:
                            sys.stdout.write(f"{line}\n")
                    sys.stdout.flush()
        except Exception:  # noqa: BLE001
            self.handleError(record)


class FileActionFormatter(logging.Formatter):
    """Formats log records for file output without ANSI codes or markup."""

    def format(self, record: logging.LogRecord) -> str:
        action = getattr(record, "action", None)
        raw_msg = record.getMessage()
        clean_msg = strip_ansi(raw_msg)
        asctime = self.formatTime(record, self.datefmt or "%Y-%m-%d %H:%M:%S")

        if action:
            lines = clean_msg.splitlines()
            if not lines:
                return f"{asctime} [{record.levelname:<5}] {action:>10}:"
            first_line = f"{asctime} [{record.levelname:<5}] {action:>10}: {lines[0]}"
            if len(lines) == 1:
                return first_line
            indent_pad = " " * 12
            rest = [f"{asctime} [{record.levelname:<5}] {indent_pad}{line}" for line in lines[1:]]
            return "\n".join([first_line, *rest])
        else:
            lines = clean_msg.splitlines()
            if not lines:
                return ""
            return "\n".join([f"{asctime} [{record.levelname:<5}] {line}" for line in lines])


# Core package logger
logger = logging.getLogger("puild")
logger.setLevel(logging.INFO)
# Attach default console handler
_default_console_handler = ConsoleActionHandler()
logger.addHandler(_default_console_handler)


def configure_logging(
    log_file: str | Path | None = None,
    level: int | str = logging.INFO,
    console: bool = True,
    file_mode: str = "a",
    max_bytes: int = 0,
    backup_count: int = 0,
    datefmt: str = "%Y-%m-%d %H:%M:%S",
) -> logging.Logger:
    """Configure puild logger to console and an optional file destination."""
    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(level)

    # Clean and close existing handlers
    for h in logger.handlers:
        h.close()
    logger.handlers.clear()

    if console:
        c_handler = ConsoleActionHandler()
        c_handler.setLevel(level)
        logger.addHandler(c_handler)

    if log_file:
        p = Path(log_file)
        p.parent.mkdir(parents=True, exist_ok=True)
        if max_bytes > 0:
            f_handler = RotatingFileHandler(
                p, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
            )
        else:
            f_handler = logging.FileHandler(p, mode=file_mode, encoding="utf-8")
        f_handler.setLevel(level)
        f_handler.setFormatter(FileActionFormatter(datefmt=datefmt))
        logger.addHandler(f_handler)

    return logger


def log_action(
    action_name: str,
    action_message: str,
    action_color: ActionColor = "white",
    level: int = logging.INFO,
) -> None:
    """Log an action using the standard puild logger."""
    if action_name in ("Failed", "Error"):
        level = logging.ERROR
    logger.log(
        level,
        action_message,
        extra={"action": action_name, "color": action_color},
    )


def log_indented(
    message: str,
    indent: str | None = None,
    stream: Any = sys.stdout,
    level: int = logging.INFO,
) -> None:
    """Log multiline text with each line indented."""
    if not message:
        return
    eff_indent = _DEFAULT_INDENT if indent is None else indent
    if stream is not sys.stdout:
        for line in message.splitlines():
            if not line.strip():
                stream.write("\n")
            else:
                stream.write(f"{eff_indent}{line}\n")
        stream.flush()
        return

    lines: list[str] = []
    for line in message.splitlines():
        if not line.strip():
            lines.append("")
        else:
            lines.append(f"{eff_indent}{line}")
    formatted = "\n".join(lines)
    logger.log(level, formatted, extra={"is_indented": True})


def write_stream_to_file_handlers(text: str) -> None:
    """Write streaming command line output directly to registered FileHandlers."""
    clean = strip_ansi(text)
    for h in logger.handlers:
        if isinstance(h, logging.FileHandler) and h.stream is not None:
            with contextlib.suppress(OSError):
                h.stream.write(clean)
                h.stream.flush()
