"""Integration test: editing a raw document's payload on real Mongo.

Skipped automatically when Docker/testcontainers is unavailable (see the
unification conftest pattern). Proves replace_payload mutates only the payload,
preserves the natural key, sets edited_at, and 404s for an unknown key.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio

from fdp_ingestion.ports import RawRecord
from fdp_ingestion.raw_repository import RawRepository
from fdp_shared.domain import SourceName

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def db() -> AsyncIterator[Any]:
    try:
        from pymongo import AsyncMongoClient
        from testcontainers.mongodb import MongoDbContainer
    except Exception as exc:
        pytest.skip(f"testcontainers/pymongo unavailable: {exc}")

    try:
        container = MongoDbContainer("mongo:7")
        container.start()
    except Exception as exc:
        pytest.skip(f"Docker unavailable for testcontainers: {exc}")

    client: AsyncMongoClient[Any] = AsyncMongoClient(container.get_connection_url())
    try:
        yield client["test"]
    finally:
        await client.close()
        container.stop()


async def test_replace_payload_edits_only_payload(db: Any) -> None:
    repo = RawRepository(db)
    await repo.upsert_many(
        [
            RawRecord(
                source=SourceName.UNDERSTAT,
                entity="match",
                source_ref="1",
                payload={"id": "1", "home": "A"},
            )
        ]
    )

    updated = await repo.replace_payload(
        SourceName.UNDERSTAT, "match", "1", {"id": "1", "home": "EDITED"}
    )
    assert updated is not None
    assert updated["payload"]["home"] == "EDITED"
    assert updated["entity"] == "match"
    assert updated["source_ref"] == "1"
    assert "edited_at" in updated


async def test_replace_payload_missing_returns_none(db: Any) -> None:
    repo = RawRepository(db)
    result = await repo.replace_payload(SourceName.UNDERSTAT, "match", "nope", {"x": 1})
    assert result is None
