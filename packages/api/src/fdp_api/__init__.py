"""API bounded context: routers, query parsing, error handling, middleware."""

from fdp_api.errors import register_error_handlers
from fdp_api.middleware import RequestIdMiddleware
from fdp_api.routers import (
    browse,
    health,
    ingestion,
    pipelines,
    raw,
    runs,
    tools,
    unified,
)

__all__ = [
    "RequestIdMiddleware",
    "browse",
    "health",
    "ingestion",
    "pipelines",
    "raw",
    "register_error_handlers",
    "runs",
    "tools",
    "unified",
]
