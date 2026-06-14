"""FastAPI routers (controllers)."""

from fdp_api.routers import (
    aggregate,
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
    "aggregate",
    "browse",
    "health",
    "ingestion",
    "pipelines",
    "raw",
    "runs",
    "tools",
    "unified",
]
