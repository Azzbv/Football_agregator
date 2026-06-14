"""Pipeline run history + single-record lineage endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from fdp_api import dependencies as deps
from fdp_unification.orchestration.models import LineageDoc, PipelineRun
from fdp_unification.orchestration.repository import (
    LineageRepository,
    PipelineRunRepository,
)

router = APIRouter(tags=["runs"])

RunRepoDep = Annotated[PipelineRunRepository, Depends(deps.get_run_repository)]
LineageRepoDep = Annotated[LineageRepository, Depends(deps.get_lineage_repository)]


@router.get("/api/pipeline-runs", response_model=list[PipelineRun])
async def list_runs(
    repo: RunRepoDep,
    pipeline_id: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[PipelineRun]:
    return await repo.list(pipeline_id=pipeline_id, limit=limit)


@router.get("/api/pipeline-runs/{run_id}", response_model=PipelineRun)
async def get_run(repo: RunRepoDep, run_id: str) -> PipelineRun:
    return await repo.get(run_id)


@router.get("/api/lineage", response_model=LineageDoc)
async def get_lineage(
    repo: LineageRepoDep,
    target: Annotated[str, Query(description="Target collection")],
    id: Annotated[str, Query(description="Target record id")],
) -> LineageDoc:
    return await repo.for_target(target, id)
