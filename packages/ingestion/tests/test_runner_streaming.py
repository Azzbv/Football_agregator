"""Runner streaming tests: bounded-memory batching + in-memory hand-off.

Proves the runner (a) flushes in batches of ``batch_size`` rather than buffering
the whole source, and (b) publishes the just-ingested records ON the event so
unification can map them WITHOUT reading them back from Mongo.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from fdp_ingestion.events import EventBus, RawIngested
from fdp_ingestion.ports import RawRecord
from fdp_ingestion.runner import IngestionRunner
from fdp_ingestion.status import RunStatus
from fdp_shared.domain import SourceName

pytestmark = pytest.mark.asyncio


class _FakeAdapter:
    """Yields ``n`` match records; tracks nothing else."""

    def __init__(self, n: int) -> None:
        self._n = n

    @property
    def name(self) -> SourceName:
        return SourceName.STATSBOMB

    @property
    def extracted_fields(self) -> dict[str, tuple[str, ...]]:
        return {"matches": ("id",)}

    async def fetch(self) -> AsyncIterator[RawRecord]:
        for i in range(self._n):
            yield RawRecord(
                source=self.name, entity="matches", source_ref=str(i), payload={"id": i}
            )


class _FakeRawRepo:
    """Records each upsert batch; never serves reads (read-back would fail)."""

    def __init__(self) -> None:
        self.batches: list[int] = []

    async def upsert_many(self, records: list[RawRecord]) -> int:
        self.batches.append(len(records))
        return len(records)


class _FakeStatusRepo:
    def __init__(self) -> None:
        self.finished: RunStatus | None = None

    async def start(self, source: SourceName) -> str:
        return "run-1"

    async def finish(self, run_id: str, *, status: RunStatus, record_count: int, **_: object) -> None:
        self.finished = status


async def test_runner_streams_in_batches_and_hands_records_inline() -> None:
    received: list[RawIngested] = []
    bus = EventBus()

    async def _capture(event: RawIngested) -> None:
        received.append(event)

    bus.subscribe(_capture)

    raw_repo = _FakeRawRepo()
    status_repo = _FakeStatusRepo()
    runner = IngestionRunner(raw_repo, status_repo, bus, batch_size=10)  # type: ignore[arg-type]

    total = await runner.run_source(_FakeAdapter(25))

    assert total == 25
    assert status_repo.finished is RunStatus.SUCCESS
    # 25 records, batch size 10 -> flushes of 10, 10, 5 (bounded memory).
    assert raw_repo.batches == [10, 10, 5]
    # Every event carried its records IN MEMORY (no Mongo read-back needed).
    assert [len(e.records) for e in received] == [10, 10, 5]
    assert all(isinstance(r, RawRecord) for e in received for r in e.records)
    # source_refs still present as the lightweight id list / replay fallback.
    assert received[0].source_refs == tuple(str(i) for i in range(10))
