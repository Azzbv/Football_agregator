"""Ingestion control + status endpoints.

``POST /api/ingestion/run`` triggers a batch ingestion (all enabled sources, or
one named source) and returns per-source written counts. ``GET
/api/ingestion/runs`` lists recent ingestion_runs audit records. The runner and
adapter factory are taken from app state so the API doesn't own ingestion wiring.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from fdp_api import dependencies as deps
from fdp_ingestion.status import IngestionRun, IngestionStatusRepository
from fdp_shared.domain import SourceName
from fdp_shared.exceptions import ValidationFailedError

router = APIRouter(prefix="/api/ingestion", tags=["ingestion"])


class RunResult(BaseModel):
    written: dict[str, int]


@router.post("/run", response_model=RunResult)
async def trigger_run(
    request: Request,
    source: Annotated[str | None, Query(description="Optional single source")] = None,
) -> RunResult:
    # The composition root attaches a zero-arg factory that builds adapters
    # (with their PoliteClients) and the runner. Keeps API free of HTTP wiring.
    build_adapters = request.app.state.build_adapters
    runner = request.app.state.ingestion_runner

    adapters = build_adapters()
    if source is not None:
        try:
            wanted = SourceName(source)
        except ValueError as exc:
            raise ValidationFailedError(f"unknown source {source!r}") from exc
        adapters = [a for a in adapters if a.name is wanted]

    written = await runner.run_all(adapters)
    return RunResult(written=written)


@router.get("/runs", response_model=list[IngestionRun])
async def list_runs(
    status_repo: Annotated[
        IngestionStatusRepository, Depends(deps.get_status_repository)
    ],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[IngestionRun]:
    return await status_repo.list_recent(limit)
