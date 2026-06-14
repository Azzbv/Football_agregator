"""Unification service: the consumer side of the ACL.

Reads raw records (either directly or in response to a :class:`RawIngested`
event), runs them through the source's ACL mapper, and upserts the resulting
unified models into the normalized collections. This is the only place that
knows how raw turns into unified, keeping that knowledge out of ingestion and
the API.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from typing import Any

from pymongo.asynchronous.database import AsyncDatabase

from fdp_ingestion.events import RawIngested
from fdp_ingestion.ports import RawRecord
from fdp_ingestion.raw_repository import raw_collection_name
from fdp_shared.domain import (
    Event,
    Match,
    Player,
    PlayerStats,
    SourceName,
    TeamStats,
)
from fdp_shared.exceptions import ValidationFailedError
from fdp_shared.logging import get_logger
from fdp_unification.mappers import get_mapper
from fdp_unification.repository import UnifiedRepository

logger = get_logger(__name__)

# Collection -> model, used to build typed repositories on demand.
_MODELS: dict[str, type[Any]] = {
    "matches": Match,
    "events": Event,
    "players": Player,
    "team_stats": TeamStats,
    "player_stats": PlayerStats,
}


class UnificationService:
    """Maps raw records to unified models and persists them."""

    def __init__(self, db: AsyncDatabase[Mapping[str, Any]]) -> None:
        self._db = db
        self._repos: dict[str, UnifiedRepository[Any]] = {}

    def _repo(self, collection: str) -> UnifiedRepository[Any]:
        if collection not in self._repos:
            self._repos[collection] = UnifiedRepository(self._db, collection, _MODELS[collection])
        return self._repos[collection]

    async def unify_records(self, records: list[RawRecord]) -> int:
        """Map and upsert a batch of raw records. Returns unified docs written."""

        by_collection: dict[str, list[Any]] = defaultdict(list)
        for record in records:
            mapper = get_mapper(record.source)
            try:
                for collection, model in mapper.map(record):
                    by_collection[collection].append(model)
            except ValidationFailedError as exc:
                logger.warning(
                    "unification_skipped",
                    source=record.source.value,
                    ref=record.source_ref,
                    error=str(exc),
                )

        written = 0
        for collection, models in by_collection.items():
            written += await self._repo(collection).upsert_many(models)
        if written:
            logger.info("unified_written", count=written)
        return written

    async def handle_raw_ingested(self, event: RawIngested) -> None:
        """EventBus handler: fetch the just-ingested raw docs and unify them.

        Decouples unification from ingestion — ingestion only publishes the
        event. Fast path: the event carries the just-written records in memory,
        so we map them directly with NO read-back from Mongo. Fallback: if the
        event has no inline records (e.g. a replayed/outbox event), re-query the
        raw collection by the refs it names.
        """

        if event.records:
            await self.unify_records(list(event.records))
            return

        col = self._db[raw_collection_name(event.source)]
        cursor = col.find(
            {"entity": event.entity, "source_ref": {"$in": list(event.source_refs)}},
            {"_id": 0},
        )
        records = [
            RawRecord(
                source=event.source,
                entity=doc["entity"],
                source_ref=doc["source_ref"],
                payload=doc["payload"],
            )
            async for doc in cursor
        ]
        await self.unify_records(records)

    async def reunify_source(self, source: SourceName, *, batch_size: int = 500) -> int:
        """Re-run unification over all stored raw docs for a source (backfill).

        Cursor-streams in batches so it never materialises the whole raw
        collection in memory — safe for millions of event docs.
        """

        col = self._db[raw_collection_name(source)]
        total = 0
        batch: list[RawRecord] = []

        async def flush() -> int:
            nonlocal batch
            if not batch:
                return 0
            written = await self.unify_records(batch)
            batch = []
            return written

        async for doc in col.find({}, {"_id": 0}):
            batch.append(
                RawRecord(
                    source=source,
                    entity=doc["entity"],
                    source_ref=doc["source_ref"],
                    payload=doc["payload"],
                )
            )
            if len(batch) >= batch_size:
                total += await flush()
        total += await flush()
        return total
