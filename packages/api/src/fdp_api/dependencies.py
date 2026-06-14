"""Dependency-injection providers.

The composition root (``app``) stores shared singletons (the AsyncMongoClient,
the database handle) on ``app.state``; these provider functions expose them to
routers via FastAPI ``Depends``. Routers never construct infrastructure
themselves — they only declare what they need. This keeps the API package free
of wiring concerns and makes ports swappable in tests.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any

from fastapi import Depends, Request
from pymongo.asynchronous.database import AsyncDatabase

from fdp_ingestion.raw_repository import RawRepository
from fdp_ingestion.status import IngestionStatusRepository
from fdp_shared.domain import Event, Match, Player, PlayerStats, TeamStats
from fdp_unification.orchestration.executor import PipelineExecutor
from fdp_unification.orchestration.repository import (
    LineageRepository,
    PipelineRepository,
    PipelineRunRepository,
)
from fdp_unification.aggregate import MatchAggregateRepository
from fdp_unification.repository import UnifiedRepository


def get_db(request: Request) -> AsyncDatabase[Mapping[str, Any]]:
    """Return the shared database handle from app state."""

    return request.app.state.db  # type: ignore[no-any-return]


DbDep = Annotated[AsyncDatabase[Mapping[str, Any]], Depends(get_db)]


def get_raw_repository(db: DbDep) -> RawRepository:
    return RawRepository(db)


def get_status_repository(db: DbDep) -> IngestionStatusRepository:
    return IngestionStatusRepository(db)


def get_matches_repo(db: DbDep) -> UnifiedRepository[Match]:
    return UnifiedRepository(db, "matches", Match)


def get_events_repo(db: DbDep) -> UnifiedRepository[Event]:
    return UnifiedRepository(db, "events", Event)


def get_players_repo(db: DbDep) -> UnifiedRepository[Player]:
    return UnifiedRepository(db, "players", Player)


def get_team_stats_repo(db: DbDep) -> UnifiedRepository[TeamStats]:
    return UnifiedRepository(db, "team_stats", TeamStats)


def get_player_stats_repo(db: DbDep) -> UnifiedRepository[PlayerStats]:
    return UnifiedRepository(db, "player_stats", PlayerStats)


def get_pipeline_repository(db: DbDep) -> PipelineRepository:
    return PipelineRepository(db)


def get_run_repository(db: DbDep) -> PipelineRunRepository:
    return PipelineRunRepository(db)


def get_lineage_repository(db: DbDep) -> LineageRepository:
    return LineageRepository(db)


def get_executor(db: DbDep) -> PipelineExecutor:
    return PipelineExecutor(db)


def get_aggregate_repository(db: DbDep) -> MatchAggregateRepository:
    return MatchAggregateRepository(db)
