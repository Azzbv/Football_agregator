"""Integration test: match-aggregate materialization on real Mongo.

Skipped automatically when Docker/testcontainers is unavailable (see conftest).
Proves the rebuild joins matches + team_stats + player_stats + events + the
referenced players into one document, and that get/query read it back.
"""

from __future__ import annotations

from typing import Any

import pytest

from fdp_shared.domain import (
    Event,
    Match,
    Player,
    PlayerStats,
    SourceName,
    Team,
    TeamStats,
)
from fdp_shared.mongo import ensure_indices
from fdp_shared.query import Pagination, QuerySpec
from fdp_unification.aggregate import MatchAggregateRepository
from fdp_unification.repository import UnifiedRepository

pytestmark = pytest.mark.asyncio

MID = "statsbomb:1"


async def _seed(db: Any) -> None:
    await ensure_indices(db)
    await UnifiedRepository(db, "matches", Match).upsert_many(
        [
            Match(
                source=SourceName.STATSBOMB,
                source_ref="1",
                match_id=MID,
                home_team=Team(team_id="t1", name="Home"),
                away_team=Team(team_id="t2", name="Away"),
            )
        ]
    )
    await UnifiedRepository(db, "team_stats", TeamStats).upsert_many(
        [TeamStats(source=SourceName.STATSBOMB, source_ref="ts1", match_id=MID, team_id="t1")]
    )
    await UnifiedRepository(db, "player_stats", PlayerStats).upsert_many(
        [
            PlayerStats(
                source=SourceName.STATSBOMB, source_ref="pst1", match_id=MID, player_id="p1"
            )
        ]
    )
    await UnifiedRepository(db, "events", Event).upsert_many(
        [
            Event(
                source=SourceName.STATSBOMB,
                source_ref="e1",
                event_id="e1",
                match_id=MID,
                event_type="shot",
                player_id="p1",
            )
        ]
    )
    await UnifiedRepository(db, "players", Player).upsert_many(
        [Player(source=SourceName.STATSBOMB, source_ref="p1", player_id="p1", name="Player One")]
    )


async def test_rebuild_materializes_full_aggregate(db: Any) -> None:
    await _seed(db)
    repo = MatchAggregateRepository(db)

    written = await repo.rebuild()
    assert written == 1

    agg = await repo.get(MID)
    assert agg.match_id == MID
    assert agg.match.home_team.name == "Home"
    assert len(agg.team_stats) == 1
    assert len(agg.player_stats) == 1
    assert agg.total_events == 1
    assert {p.player_id for p in agg.players} == {"p1"}


async def test_rebuild_is_idempotent_and_queryable(db: Any) -> None:
    await _seed(db)
    repo = MatchAggregateRepository(db)

    await repo.rebuild()
    await repo.rebuild()

    page = await repo.query(QuerySpec(pagination=Pagination(page=1, size=50)))
    assert page.total == 1
    assert page.items[0].match_id == MID
