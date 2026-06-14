"""Shared kernel: config, logging, Mongo client, domain DTOs, exceptions.

This package is the only one allowed to be imported by every other bounded
context. It must remain free of inbound dependencies on ingestion/unification/
api/app to avoid coupling the contexts together.
"""

from fdp_shared.config import Settings, get_settings
from fdp_shared.exceptions import (
    FdpError,
    IngestionError,
    NotFoundError,
    ValidationFailedError,
)
from fdp_shared.logging import configure_logging, get_logger

__all__ = [
    "FdpError",
    "IngestionError",
    "NotFoundError",
    "Settings",
    "ValidationFailedError",
    "configure_logging",
    "get_logger",
    "get_settings",
]