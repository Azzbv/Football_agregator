"""Unified browse endpoints.

One router covering /matches, /events, /players, /team-stats, /player-stats.
Each supports filtering (allow-listed fields), 1-indexed pagination and
multi-field sort. Responses are typed PageResponse envelopes of unified DTOs.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from fdp_api import dependencies as deps
from fdp_api.params import PageParam, SizeParam, SortParam, build_spec
from fdp_api.schemas import PageResponse
from fdp_shared.domain import Event, Match, Player, PlayerStats, TeamStats
from fdp_unification.repository import UnifiedRepository

router = APIRouter(prefix="/api", tags=["unified"])


@router.get("/matches", response_model=PageResponse[Match])
async def list_matches(
    repo: Annotated[UnifiedRepository[Match], Depends(deps.get_matches_repo)],
    page: PageParam = 1,
    size: SizeParam = 20,
    sort: SortParam = None,
    source: Annotated[str | None, Query()] = None,
    league_id: Annotated[str | None, Query()] = None,
    season_id: Annotated[str | None, Query()] = None,
    competition: Annotated[str | None, Query()] = None,
) -> PageResponse[Match]:
    allowed = {"source", "league_id", "season_id", "competition", "match_id", "match_date"}
    filters: dict[str, Any] = {
        "source": source,
        "league_id": league_id,
        "season_id": season_id,
        "competition": competition,
    }
    spec = build_spec(page=page, size=size, sort=sort, filters=filters, allowed_fields=allowed)
    return PageResponse.from_page(await repo.query(spec))


@router.get("/events", response_model=PageResponse[Event])
async def list_events(
    repo: Annotated[UnifiedRepository[Event], Depends(deps.get_events_repo)],
    page: PageParam = 1,
    size: SizeParam = 20,
    sort: SortParam = None,
    match_id: Annotated[str | None, Query()] = None,
    player_id: Annotated[str | None, Query()] = None,
    event_type: Annotated[str | None, Query()] = None,
    source: Annotated[str | None, Query()] = None,
) -> PageResponse[Event]:
    allowed = {"match_id", "player_id", "event_type", "team_id", "source"}
    filters: dict[str, Any] = {
        "match_id": match_id,
        "player_id": player_id,
        "event_type": event_type,
        "source": source,
    }
    spec = build_spec(page=page, size=size, sort=sort, filters=filters, allowed_fields=allowed)
    return PageResponse.from_page(await repo.query(spec))


@router.get("/players", response_model=PageResponse[Player])
async def list_players(
    repo: Annotated[UnifiedRepository[Player], Depends(deps.get_players_repo)],
    page: PageParam = 1,
    size: SizeParam = 20,
    sort: SortParam = None,
    player_id: Annotated[str | None, Query()] = None,
    country: Annotated[str | None, Query()] = None,
    source: Annotated[str | None, Query()] = None,
) -> PageResponse[Player]:
    allowed = {"player_id", "country", "position", "source", "name"}
    filters: dict[str, Any] = {"player_id": player_id, "country": country, "source": source}
    spec = build_spec(page=page, size=size, sort=sort, filters=filters, allowed_fields=allowed)
    return PageResponse.from_page(await repo.query(spec))


@router.get("/team-stats", response_model=PageResponse[TeamStats])
async def list_team_stats(
    repo: Annotated[UnifiedRepository[TeamStats], Depends(deps.get_team_stats_repo)],
    page: PageParam = 1,
    size: SizeParam = 20,
    sort: SortParam = None,
    team_id: Annotated[str | None, Query()] = None,
    match_id: Annotated[str | None, Query()] = None,
    season_id: Annotated[str | None, Query()] = None,
    source: Annotated[str | None, Query()] = None,
) -> PageResponse[TeamStats]:
    allowed = {"team_id", "match_id", "season_id", "league_id", "source"}
    filters: dict[str, Any] = {
        "team_id": team_id,
        "match_id": match_id,
        "season_id": season_id,
        "source": source,
    }
    spec = build_spec(page=page, size=size, sort=sort, filters=filters, allowed_fields=allowed)
    return PageResponse.from_page(await repo.query(spec))


@router.get("/player-stats", response_model=PageResponse[PlayerStats])
async def list_player_stats(
    repo: Annotated[UnifiedRepository[PlayerStats], Depends(deps.get_player_stats_repo)],
    page: PageParam = 1,
    size: SizeParam = 20,
    sort: SortParam = None,
    player_id: Annotated[str | None, Query()] = None,
    match_id: Annotated[str | None, Query()] = None,
    team_id: Annotated[str | None, Query()] = None,
    source: Annotated[str | None, Query()] = None,
) -> PageResponse[PlayerStats]:
    allowed = {"player_id", "match_id", "team_id", "season_id", "league_id", "source"}
    filters: dict[str, Any] = {
        "player_id": player_id,
        "match_id": match_id,
        "team_id": team_id,
        "source": source,
    }
    spec = build_spec(page=page, size=size, sort=sort, filters=filters, allowed_fields=allowed)
    return PageResponse.from_page(await repo.query(spec))
