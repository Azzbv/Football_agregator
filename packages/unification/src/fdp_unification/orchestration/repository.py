"""Repositories for pipeline definitions, runs, and lineage.

Repository pattern over the PyMongo Async driver (consistent with the rest of
the platform). Documents are keyed by the model's own ``id`` field (a uuid hex),
not Mongo's ``_id``, so the API never leaks persistence internals.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from pymongo import ASCENDING, DESCENDING
from pymongo.asynchronous.database import AsyncDatabase

from fdp_shared.exceptions import NotFoundError

from fdp_unification.orchestration.models import LineageDoc, Pipeline, PipelineRun


class PipelineRepository:
    """CRUD over the ``pipelines`` collection."""

    COLLECTION = "pipelines"

    def __init__(self, db: AsyncDatabase[Mapping[str, Any]]) -> None:
        self._col = db[self.COLLECTION]

    async def ensure_indices(self) -> None:
        await self._col.create_index([("id", ASCENDING)], unique=True, name="uq_pipeline_id")

    async def create(self, pipeline: Pipeline) -> Pipeline:
        now = datetime.now(UTC)
        pipeline.created_at = now
        pipeline.updated_at = now
        await self._col.insert_one(pipeline.model_dump(mode="json"))
        return pipeline

    async def get(self, pipeline_id: str) -> Pipeline:
        doc = await self._col.find_one({"id": pipeline_id}, {"_id": 0})
        if doc is None:
            raise NotFoundError(f"pipeline {pipeline_id!r} not found")
        return Pipeline.model_validate(doc)

    async def list(self) -> list[Pipeline]:
        return [Pipeline.model_validate(d) async for d in self._col.find({}, {"_id": 0})]

    async def update(self, pipeline_id: str, pipeline: Pipeline) -> Pipeline:
        pipeline.id = pipeline_id
        pipeline.updated_at = datetime.now(UTC)
        result = await self._col.update_one(
            {"id": pipeline_id},
            {"$set": pipeline.model_dump(mode="json", exclude={"created_at"})},
        )
        if result.matched_count == 0:
            raise NotFoundError(f"pipeline {pipeline_id!r} not found")
        return await self.get(pipeline_id)

    async def delete(self, pipeline_id: str) -> None:
        result = await self._col.delete_one({"id": pipeline_id})
        if result.deleted_count == 0:
            raise NotFoundError(f"pipeline {pipeline_id!r} not found")


class PipelineRunRepository:
    """Read/write over the ``pipeline_runs`` collection."""

    COLLECTION = "pipeline_runs"

    def __init__(self, db: AsyncDatabase[Mapping[str, Any]]) -> None:
        self._col = db[self.COLLECTION]

    async def ensure_indices(self) -> None:
        await self._col.create_index([("id", ASCENDING)], unique=True, name="uq_run_id")
        await self._col.create_index([("pipeline_id", ASCENDING), ("started_at", DESCENDING)])

    async def save(self, run: PipelineRun) -> PipelineRun:
        await self._col.update_one(
            {"id": run.id}, {"$set": run.model_dump(mode="json")}, upsert=True
        )
        return run

    async def get(self, run_id: str) -> PipelineRun:
        doc = await self._col.find_one({"id": run_id}, {"_id": 0})
        if doc is None:
            raise NotFoundError(f"run {run_id!r} not found")
        return PipelineRun.model_validate(doc)

    async def list(self, *, pipeline_id: str | None = None, limit: int = 50) -> list[PipelineRun]:
        query = {"pipeline_id": pipeline_id} if pipeline_id else {}
        cursor = self._col.find(query, {"_id": 0}).sort("started_at", DESCENDING).limit(limit)
        return [PipelineRun.model_validate(d) async for d in cursor]


class LineageRepository:
    """Read over the dedicated ``lineage`` collection."""

    COLLECTION = "lineage"

    def __init__(self, db: AsyncDatabase[Mapping[str, Any]]) -> None:
        self._col = db[self.COLLECTION]

    async def ensure_indices(self) -> None:
        await self._col.create_index(
            [("target_collection", ASCENDING), ("target_id", ASCENDING)],
            unique=True,
            name="uq_lineage_target",
        )

    async def for_target(self, target_collection: str, target_id: str) -> LineageDoc:
        doc = await self._col.find_one(
            {"target_collection": target_collection, "target_id": target_id}, {"_id": 0}
        )
        if doc is None:
            raise NotFoundError(
                f"no lineage for {target_collection}/{target_id}"
            )
        return LineageDoc.model_validate(doc)
