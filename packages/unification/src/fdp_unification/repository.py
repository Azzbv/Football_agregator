"""Repository over the unified, normalized collections.

Generic over the unified Pydantic model type. Upserts use the per-collection
unique key (defined in :mod:`fdp_shared.mongo`) so re-unifying is idempotent.
Reads support the shared :class:`QuerySpec` (filter + multi-field sort +
pagination) and always return validated DTOs — never raw persistence docs.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel
from pymongo import UpdateOne
from pymongo.asynchronous.database import AsyncDatabase

from fdp_shared.logging import get_logger
from fdp_shared.query import Page, QuerySpec

logger = get_logger(__name__)

# Maps collection -> the field(s) that form its unique upsert key.
_KEY_FIELDS: dict[str, tuple[str, ...]] = {
    "matches": ("match_id",),
    "events": ("event_id",),
    "players": ("player_id",),
    "team_stats": ("team_id", "match_id"),
    "player_stats": ("player_id", "match_id"),
}


class UnifiedRepository[TModel: BaseModel]:
    """Typed repository for one unified collection."""

    def __init__(
        self,
        db: AsyncDatabase[Mapping[str, Any]],
        collection: str,
        model: type[TModel],
    ) -> None:
        self._col = db[collection]
        self._collection = collection
        self._model = model
        self._key_fields = _KEY_FIELDS[collection]

    def _key(self, doc: dict[str, Any]) -> dict[str, Any]:
        return {f: doc.get(f) for f in self._key_fields}

    async def upsert_many(self, models: list[TModel]) -> int:
        if not models:
            return 0
        ops = []
        for m in models:
            doc = m.model_dump(mode="json")
            ops.append(UpdateOne(self._key(doc), {"$set": doc}, upsert=True))
        result = await self._col.bulk_write(ops, ordered=False)
        return result.upserted_count + result.modified_count

    async def query(self, spec: QuerySpec) -> Page[TModel]:
        """Run a filter/sort/paginate query and return validated DTOs."""

        total = await self._col.count_documents(spec.filters)
        cursor = self._col.find(spec.filters, {"_id": 0})
        if spec.sort:
            cursor = cursor.sort(spec.mongo_sort())
        cursor = cursor.skip(spec.pagination.skip).limit(spec.pagination.limit)

        items = [self._model.model_validate(doc) async for doc in cursor]
        return Page[TModel](
            items=items,
            page=spec.pagination.page,
            size=spec.pagination.size,
            total=total,
        )
