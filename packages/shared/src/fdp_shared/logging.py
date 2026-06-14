"""Structured logging setup using structlog.

In the ``prod`` profile logs are rendered as JSON; in ``local`` they are
rendered as colourised key/value console lines. A request-id (and any other
bound context) is propagated via ``structlog.contextvars`` so the API
middleware can bind a request id once and have it appear on every log line.
"""

from __future__ import annotations

import logging
import sys

import structlog

from fdp_shared.config import Profile


def configure_logging(profile: Profile, log_level: str = "INFO") -> None:
    """Configure structlog + stdlib logging once at startup.

    Idempotent enough for repeated calls in tests; the last call wins.
    """

    level = getattr(logging, log_level.upper(), logging.INFO)

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if profile is Profile.PROD:
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )

    # Route stdlib logging (uvicorn, pymongo) through the same level threshold.
    logging.basicConfig(level=level, stream=sys.stderr, format="%(message)s")


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger."""

    return structlog.get_logger(name)  # type: ignore[no-any-return]
