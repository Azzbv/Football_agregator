"""Integration test: preview (no writes) + commit run (upsert + lineage persist).

Skipped automatically when Docker/testcontainers is unavailable (see conftest).
Proves the two executor modes against real Mongo and that the dedicated lineage
collection is populated and queryable for a unified record.
"""

from __future__ import annotations

from typing import Any

import pytest

from fdp_unification.orchestration.executor import PipelineExecutor
from fdp_unification.orchestration.models import Pipeline, StepConfig
from fdp_unification.orchestration.repository import LineageRepository

pytestmark = pytest.mark.asyncio


def _pipeline() -> Pipeline:
    return Pipeline(
        name="understat-matches",
        source_collection="raw_understat",
        target_collection="matches",
        upsert_key=["match_id"],
        steps=[
            StepConfig(type="extract", config={"source_path": "payload.id", "target_path": "match_id"}),
            StepConfig(type="extract", config={"source_path": "payload.h.title", "target_path": "home"}),
            StepConfig(type="constant", config={"target_path": "source", "value": "understat"}),
            StepConfig(type="filter", config={"target_path": "match_id", "op": "exists"}),
        ],
    )


async def _seed(db: Any) -> None:
    await db["raw_understat"].insert_many(
        [
            {"entity": "matches", "source_ref": "1001", "payload": {"id": "1001", "h": {"title": "Arsenal"}}},
            {"entity": "matches", "source_ref": "1002", "payload": {"id": "1002", "h": {"title": "Liverpool"}}},
        ]
    )


async def test_preview_does_not_write(db: Any) -> None:
    await _seed(db)
    executor = PipelineExecutor(db)
    items = await executor.preview(_pipeline(), limit=10)

    assert len(items) == 2
    assert items[0].output is not None
    assert items[0].output["match_id"] in {"1001", "1002"}
    assert items[0].lineage  # lineage captured per record
    # Dry-run wrote nothing to the target.
    assert await db["matches"].count_documents({}) == 0


async def test_run_upserts_and_persists_lineage(db: Any) -> None:
    await _seed(db)
    executor = PipelineExecutor(db)
    pipeline = _pipeline()

    run = await executor.run(pipeline)
    assert run.output_count == 2
    assert await db["matches"].count_documents({}) == 2

    # Re-run is idempotent (upsert by match_id), not duplicating.
    await executor.run(pipeline)
    assert await db["matches"].count_documents({}) == 2

    # Lineage persisted and queryable for one unified record.
    lineage_repo = LineageRepository(db)
    doc = await lineage_repo.for_target("matches", "1001")
    assert doc.source_collection == "raw_understat"
    assert any(e.target_path == "match_id" for e in doc.entries)
    assert any(e.target_path == "home" and e.after_value == "Arsenal" for e in doc.entries)
