"""Structured logging setup.

All log output goes through structlog, JSON-formatted by default.
Use get_logger(__name__) in modules.
"""

from __future__ import annotations

import logging
import sys
from typing import TextIO

import structlog


def configure_logging(
    level: str = "INFO",
    stream: TextIO | None = None,
    json_output: bool = True,
) -> None:
    """Configure structlog + stdlib logging. Call once at process start."""
    stream = stream or sys.stderr
    logging.basicConfig(
        format="%(message)s",
        stream=stream,
        level=getattr(logging, level.upper()),
    )

    processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    if json_output:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level.upper())),
        logger_factory=structlog.PrintLoggerFactory(file=stream),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a bound logger. Modules call ``log = get_logger(__name__)`` at top."""
    return structlog.get_logger(name)
