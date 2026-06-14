"""Health and readiness endpoints for container orchestration.

``/health`` is a cheap liveness probe (process is up). ``/health/ready`` is a
readiness probe that round-trips a Mongo ping, so orchestrators only route
traffic once the DB connection is actually usable.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel

from fdp_api import dependencies as deps
from fdp_shared.mongo import ping

router = APIRouter(tags=["health"])


class Health(BaseModel):
    status: str


@router.get("/health", response_model=Health)
async def health() -> Health:
    return Health(status="ok")


@router.get("/health/ready", response_model=Health)
async def ready(db: deps.DbDep, response: Response) -> Health:
    try:
        await ping(db.client)
    except Exception:  # noqa: BLE001 - any failure means not-ready.
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return Health(status="not-ready")
    return Health(status="ready")
