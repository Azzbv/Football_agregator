"""Materialized match-aggregate repository.

Builds the denormalized ``match_aggregates`` collection by joining the
normalized unified collections on ``match_id``: each fixture is stored with its
team_stats, player_stats, events and the players those reference embedded in one
document. Reads serve that materialized document directly; ``rebuild`` is the
idempotent (re)materialization, intended to run on demand or after ingestion.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from pymongo import ASCENDING, UpdateOne
from pymongo.asynchronous.database import AsyncDatabase

from fdp_shared.domain import (
    Event,
    Match,
    MatchAggregate,
    Player,
    PlayerStats,
    TeamStats,
)
from fdp_shared.exceptions import NotFoundError
from fdp_shared.logging import get_logger
from fdp_shared.query import Page, QuerySpec

logger = get_logger(__name__)

_COLLECTION = "match_aggregates"


class MatchAggregateRepository:
    """Materializes and serves the ``match_aggregates`` collection."""

    def __init__(self, db: AsyncDatabase[Mapping[str, Any]]) -> None:
        self._db = db
        self._col = db[_COLLECTION]

    async def build_one(self, match_id: str) -> MatchAggregate | None:
        """Assemble (without persisting) the aggregate for one match_id."""

        match_doc = await self._db["matches"].find_one({"match_id": match_id}, {"_id": 0})
        if match_doc is None:
            return None

        team_stats = [
            TeamStats.model_validate(d)
            async for d in self._db["team_stats"].find({"match_id": match_id}, {"_id": 0})
        ]
        player_stats = [
            PlayerStats.model_validate(d)
            async for d in self._db["player_stats"].find({"match_id": match_id}, {"_id": 0})
        ]
        events = [
            Event.model_validate(d)
            async for d in self._db["events"].find({"match_id": match_id}, {"_id": 0})
        ]

        player_ids = {e.player_id for e in events if e.player_id}
        player_ids |= {ps.player_id for ps in player_stats if ps.player_id}
        players: list[Player] = []
        if player_ids:
            players = [
                Player.model_validate(d)
                async for d in self._db["players"].find(
                    {"player_id": {"$in": sorted(player_ids)}}, {"_id": 0}
                )
            ]

        return MatchAggregate(
            match_id=match_id,
            match=Match.model_validate(match_doc),
            team_stats=team_stats,
            player_stats=player_stats,
            events=events,
            players=players,
            total_events=len(events),
            built_at=datetime.now(UTC),
        )

    async def rebuild(self, match_id: str | None = None) -> int:
        """(Re)materialize aggregates and return how many were written.

        With ``match_id`` set, rebuilds only that match; otherwise rebuilds every
        match present in the ``matches`` collection.
        """

        if match_id is not None:
            agg = await self.build_one(match_id)
            if agg is None:
                return 0
            await self._upsert(agg)
            return 1

        ops: list[UpdateOne] = []
        async for match_doc in self._db["matches"].find({}, {"_id": 0, "match_id": 1}):
            mid = match_doc.get("match_id")
            if mid is None:
                continue
            agg = await self.build_one(mid)
            if agg is None:
                continue
            ops.append(
                UpdateOne(
                    {"match_id": mid},
                    {"$set": agg.model_dump(mode="json")},
                    upsert=True,
                )
            )
        if not ops:
            logger.info("aggregate_rebuild", written=0)
            return 0
        result = await self._col.bulk_write(ops, ordered=False)
        written = result.upserted_count + result.modified_count
        logger.info("aggregate_rebuild", written=written)
        return written

    async def _upsert(self, agg: MatchAggregate) -> None:
        await self._col.update_one(
            {"match_id": agg.match_id},
            {"$set": agg.model_dump(mode="json")},
            upsert=True,
        )

    async def get(self, match_id: str) -> MatchAggregate:
        """Return the materialized aggregate, or raise NotFoundError."""

        doc = await self._col.find_one({"match_id": match_id}, {"_id": 0})
        if doc is None:
            raise NotFoundError(f"no match aggregate for match_id {match_id!r} (rebuild first)")
        return MatchAggregate.model_validate(doc)

    async def query(self, spec: QuerySpec) -> Page[MatchAggregate]:
        """Page over materialized aggregates."""

        total = await self._col.count_documents(spec.filters)
        cursor = self._col.find(spec.filters, {"_id": 0})
        cursor = cursor.sort(spec.mongo_sort() or [("match_id", ASCENDING)])
        cursor = cursor.skip(spec.pagination.skip).limit(spec.pagination.limit)
        items = [MatchAggregate.model_validate(d) async for d in cursor]
        return Page[MatchAggregate](
            items=items,
            page=spec.pagination.page,
            size=spec.pagination.size,
            total=total,
        )
