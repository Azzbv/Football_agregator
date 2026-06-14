"""Ingestion-run status tracking persisted to the ``ingestion_runs`` collection.

Every batch run records: which source, status (success/failure), record count,
start/end timestamps and an error summary. This gives operators an audit trail
of what ran and whether it succeeded.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel
from pymongo.asynchronous.database import AsyncDatabase

from fdp_shared.domain import SourceName


class RunStatus(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"


class IngestionRun(BaseModel):
    source: SourceName
    status: RunStatus
    record_count: int = 0
    started_at: datetime
    finished_at: datetime | None = None
    error_summary: str | None = None


class IngestionStatusRepository:
    """Repository over the ``ingestion_runs`` collection."""

    COLLECTION = "ingestion_runs"

    def __init__(self, db: AsyncDatabase[Mapping[str, Any]]) -> None:
        self._col = db[self.COLLECTION]

    async def start(self, source: SourceName) -> str:
        """Insert an in-progress run record; return its id."""

        doc = {
            "source": source.value,
            "status": "running",
            "record_count": 0,
            "started_at": datetime.now(UTC),
            "finished_at": None,
            "error_summary": None,
        }
        result = await self._col.insert_one(doc)
        return str(result.inserted_id)

    async def finish(
        self,
        run_id: str,
        *,
        status: RunStatus,
        record_count: int,
        error_summary: str | None = None,
    ) -> None:
        from bson import ObjectId

        await self._col.update_one(
            {"_id": ObjectId(run_id)},
            {
                "$set": {
                    "status": status.value,
                    "record_count": record_count,
                    "finished_at": datetime.now(UTC),
                    "error_summary": error_summary,
                }
            },
        )

    async def list_recent(self, limit: int = 50) -> list[IngestionRun]:
        cursor = self._col.find().sort("started_at", -1).limit(limit)
        runs: list[IngestionRun] = []
        async for raw in cursor:
            doc = dict(raw)
            doc.pop("_id", None)
            if doc.get("status") == "running":
                continue
            runs.append(IngestionRun.model_validate(doc))
        return runs
