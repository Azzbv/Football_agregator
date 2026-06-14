"""Domain exception hierarchy shared across all contexts."""

from __future__ import annotations


class FdpError(Exception):
    """Base class for all platform errors."""


class NotFoundError(FdpError):
    """A requested resource does not exist."""


class ValidationFailedError(FdpError):
    """A document failed domain/schema validation during unification."""


class IngestionError(FdpError):
    """An ingestion adapter failed to fetch or parse a source."""

    def __init__(self, source: str, message: str) -> None:
        self.source = source
        super().__init__(f"[{source}] {message}")
