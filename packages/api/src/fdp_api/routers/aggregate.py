"""Match-aggregate endpoints: the denormalized 'everything about one match' view.

Serves the materialized ``match_aggregates`` collection (one fixture with its
team_stats, player_stats, events and players embedded). ``rebuild`` (re)builds
the collection from the normalized data; it must be run after ingestion/pipeline
changes for reads to reflect them.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from fdp_api import dependencies as deps
from fdp_api.params import PageParam, SizeParam, SortParam, build_spec
from fdp_api.schemas import PageResponse
from fdp_shared.domain import MatchAggregate
from fdp_unification.aggregate import MatchAggregateRepository

router = APIRouter(prefix="/api/aggregate", tags=["aggregate"])

AggRepoDep = Annotated[MatchAggregateRepository, Depends(deps.get_aggregate_repository)]


class RebuildResult(BaseModel):
    written: int


@router.post("/rebuild", response_model=RebuildResult)
async def rebuild_aggregates(
    repo: AggRepoDep,
    match_id: Annotated[str | None, Query(description="Rebuild one match only")] = None,
) -> RebuildResult:
    return RebuildResult(written=await repo.rebuild(match_id))


@router.get("/matches", response_model=PageResponse[MatchAggregate])
async def list_aggregates(
    repo: AggRepoDep,
    page: PageParam = 1,
    size: SizeParam = 20,
    sort: SortParam = None,
) -> PageResponse[MatchAggregate]:
    allowed = {"match_id"}
    filters: dict[str, Any] = {}
    spec = build_spec(page=page, size=size, sort=sort, filters=filters, allowed_fields=allowed)
    return PageResponse.from_page(await repo.query(spec))


@router.get("/matches/{match_id}", response_model=MatchAggregate)
async def get_aggregate(repo: AggRepoDep, match_id: str) -> MatchAggregate:
    return await repo.get(match_id)
