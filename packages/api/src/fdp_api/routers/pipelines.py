"""Pipeline CRUD + preview (dry-run) + run endpoints.

* CRUD persists declarative :class:`Pipeline` definitions.
* ``preview`` runs the executor in dry-run mode against N sample records and
  returns input -> output + lineage with NO writes (the UI preview uses this).
* ``run`` executes and upserts into the target collection, persists per-record
  lineage and a :class:`PipelineRun` status record.

All step configs are validated (against the registry's per-type Pydantic models)
when the executor builds the steps, so an invalid config returns a problem+json
error rather than a 500.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends, Query

from fdp_api import dependencies as deps
from fdp_unification.orchestration.executor import PipelineExecutor
from fdp_unification.orchestration.models import (
    ErrorMode,
    Pipeline,
    PipelineRun,
    PreviewItem,
)
from fdp_unification.orchestration.repository import (
    PipelineRepository,
    PipelineRunRepository,
)

router = APIRouter(prefix="/api/pipelines", tags=["pipelines"])

PipelineRepoDep = Annotated[PipelineRepository, Depends(deps.get_pipeline_repository)]
RunRepoDep = Annotated[PipelineRunRepository, Depends(deps.get_run_repository)]
ExecutorDep = Annotated[PipelineExecutor, Depends(deps.get_executor)]


@router.get("", response_model=list[Pipeline])
async def list_pipelines(repo: PipelineRepoDep) -> list[Pipeline]:
    return await repo.list()


@router.post("", response_model=Pipeline, status_code=201)
async def create_pipeline(repo: PipelineRepoDep, pipeline: Pipeline) -> Pipeline:
    await repo.ensure_indices()
    return await repo.create(pipeline)


@router.get("/{pipeline_id}", response_model=Pipeline)
async def get_pipeline(repo: PipelineRepoDep, pipeline_id: str) -> Pipeline:
    return await repo.get(pipeline_id)


@router.put("/{pipeline_id}", response_model=Pipeline)
async def update_pipeline(
    repo: PipelineRepoDep, pipeline_id: str, pipeline: Pipeline
) -> Pipeline:
    return await repo.update(pipeline_id, pipeline)


@router.delete("/{pipeline_id}", status_code=204)
async def delete_pipeline(repo: PipelineRepoDep, pipeline_id: str) -> None:
    await repo.delete(pipeline_id)


@router.post("/{pipeline_id}/preview", response_model=list[PreviewItem])
async def preview_pipeline(
    repo: PipelineRepoDep,
    executor: ExecutorDep,
    pipeline_id: str,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> list[PreviewItem]:
    pipeline = await repo.get(pipeline_id)
    return await executor.preview(pipeline, limit=limit)


@router.post("/{pipeline_id}/run", response_model=PipelineRun)
async def run_pipeline(
    repo: PipelineRepoDep,
    run_repo: RunRepoDep,
    executor: ExecutorDep,
    pipeline_id: str,
    error_mode: Annotated[ErrorMode, Body(embed=True)] = ErrorMode.SKIP,
) -> PipelineRun:
    pipeline = await repo.get(pipeline_id)
    await run_repo.ensure_indices()
    run = await executor.run(pipeline, error_mode=error_mode)
    return await run_repo.save(run)
