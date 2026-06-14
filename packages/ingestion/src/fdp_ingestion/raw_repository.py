"""Repository over the raw, per-source collections.

Raw records are upserted into ``raw_{source}`` collections keyed by
``(entity, source_ref)`` so re-running ingestion is idempotent and never
duplicates. The payload is stored verbatim — raw means raw.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from pymongo import ASCENDING
from pymongo.asynchronous.database import AsyncDatabase

from fdp_ingestion.ports import RawRecord
from fdp_shared.domain import SourceName
from fdp_shared.logging import get_logger

logger = get_logger(__name__)


def raw_collection_name(source: SourceName) -> str:
    return f"raw_{source.value}"


class RawRepository:
    """Idempotent upsert + paginated read for raw_* collections."""

    def __init__(self, db: AsyncDatabase[Mapping[str, Any]]) -> None:
        self._db = db
        self._ensured: set[str] = set()

    async def _ensure(self, collection: str) -> None:
        if collection in self._ensured:
            return
        await self._db[collection].create_index(
            [("entity", ASCENDING), ("source_ref", ASCENDING)],
            unique=True,
            name="uq_entity_ref",
        )
        self._ensured.add(collection)

    async def upsert_many(self, records: list[RawRecord]) -> int:
        """Upsert a batch grouped by source collection. Returns count written."""

        if not records:
            return 0
        from pymongo import UpdateOne

        by_source: dict[str, list[RawRecord]] = {}
        for rec in records:
            by_source.setdefault(raw_collection_name(rec.source), []).append(rec)

        written = 0
        now = datetime.now(UTC)
        for collection, recs in by_source.items():
            await self._ensure(collection)
            ops = [
                UpdateOne(
                    {"entity": r.entity, "source_ref": r.source_ref},
                    {
                        "$set": {
                            "entity": r.entity,
                            "source_ref": r.source_ref,
                            "payload": r.payload,
                            "fetched_at": now,
                        }
                    },
                    upsert=True,
                )
                for r in recs
            ]
            result = await self._db[collection].bulk_write(ops, ordered=False)
            written += result.upserted_count + result.modified_count
        return written

    async def get_one(
        self, source: SourceName, entity: str, source_ref: str
    ) -> dict[str, Any] | None:
        col = self._db[raw_collection_name(source)]
        doc = await col.find_one({"entity": entity, "source_ref": source_ref}, {"_id": 0})
        return dict(doc) if doc is not None else None

    async def replace_payload(
        self, source: SourceName, entity: str, source_ref: str, payload: Any
    ) -> dict[str, Any] | None:
        """Replace a single raw doc's payload, addressed by its natural key.

        Only ``payload`` is mutated; the ``(entity, source_ref)`` key and an
        ``edited_at`` marker are set. Returns the updated doc, or None if absent.
        Re-running ingestion for the same key would overwrite this edit.
        """

        col = self._db[raw_collection_name(source)]
        result = await col.update_one(
            {"entity": entity, "source_ref": source_ref},
            {"$set": {"payload": payload, "edited_at": datetime.now(UTC)}},
        )
        if result.matched_count == 0:
            return None
        return await self.get_one(source, entity, source_ref)

    async def find(
        self,
        source: SourceName,
        entity: str | None,
        *,
        skip: int,
        limit: int,
        sort: list[tuple[str, int]],
    ) -> tuple[list[dict[str, Any]], int]:
        col = self._db[raw_collection_name(source)]
        query: dict[str, Any] = {}
        if entity:
            query["entity"] = entity
        total = await col.count_documents(query)
        cursor = col.find(query, {"_id": 0})
        if sort:
            cursor = cursor.sort(sort)
        cursor = cursor.skip(skip).limit(limit)
        items = [dict(doc) async for doc in cursor]
        return items, total
