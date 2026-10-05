"""Shared Loguru configuration for the Rospo compiler and assembler CLIs."""

import sys
from pathlib import Path

from loguru import logger


def configure_logging(
    name: str,
    verbosity: int,
    log_path: Path,
    *,
    diagnose: bool | None = None,
    backtrace: bool | None = None,
) -> Path:
    """Log details to a per-tool file, warnings to stdout, and errors to stderr."""
    path = log_path
    path.parent.mkdir(parents=True, exist_ok=True)
    logger.remove()
    if diagnose is None:
        diagnose = verbosity >= 3
    if backtrace is None:
        backtrace = verbosity >= 2

    def warning_format(record):
        message = f"Warning: {record['message']}"
        if verbosity >= 1:
            file = record["file"]
            message += f"\n  at {file.name}:{record['line']} in {record['function']}"
        if verbosity >= 2:
            context = record["extra"].get("diagnostic")
            if context:
                message += f"\n  source/context: {context}"
        if verbosity >= 3:
            message += f"\n  details: {record['name']} ({record['file'].path}:{record['line']})"
            message += f"\n  full log: {path}"
        return message.replace("{", "{{").replace("}", "}}")

    logger.add(
        sys.stdout,
        level="WARNING",
        filter=lambda record: record["level"].name == "WARNING",
        format=warning_format,
        colorize=True,
    )
    logger.add(
        sys.stderr,
        level="ERROR",
        format="{level}: {message}",
        colorize=True,
        backtrace=backtrace,
        diagnose=diagnose,
    )
    file_levels = ("INFO", "DEBUG", "TRACE", "TRACE")
    logger.add(
        path,
        level=file_levels[min(max(verbosity, 0), 3)],
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
        backtrace=backtrace,
        diagnose=diagnose,
        mode="w",
    )
    return path
