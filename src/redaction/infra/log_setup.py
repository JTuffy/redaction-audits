"""Structured logging with structlog, routed through the standard library.

Routing through `logging` means Inspect's own log records and ours share one handler and level.
"""

from __future__ import annotations

import logging
import sys

import structlog

from redaction.infra.settings import LogFormat

_SHARED_PROCESSORS: list[structlog.typing.Processor] = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_log_level,
    structlog.stdlib.add_logger_name,
    structlog.processors.TimeStamper(fmt="iso", utc=True),
    structlog.processors.StackInfoRenderer(),
]


def configure_logging(level: str = "INFO", fmt: LogFormat = LogFormat.CONSOLE) -> None:
    """Configure structlog and the root logger. Safe to call more than once."""
    renderer: structlog.typing.Processor = (
        structlog.processors.JSONRenderer()
        if fmt is LogFormat.JSON
        else structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())
    )
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=_SHARED_PROCESSORS,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            renderer,
        ],
    )
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())

    structlog.configure(
        processors=[*_SHARED_PROCESSORS, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """A named structured logger."""
    logger: structlog.stdlib.BoundLogger = structlog.stdlib.get_logger(name)
    return logger
