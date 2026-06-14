"""Batch ingestion runner.

Drives each :class:`SourcePort` adapter: streams its raw records, upserts them in
batches into the raw collections, records an ``ingestion_runs`` row, and publishes
a :class:`RawIngested` domain event per (source, entity) batch so the unification
context can react. Each source is isolated — one failing source records a failure
run and does not abort the others.
"""

from __future__ import annotations

from collections import defaultdict

from fdp_ingestion.events import EventBus, RawIngested
from fdp_ingestion.ports import RawRecord, SourcePort
from fdp_ingestion.raw_repository import RawRepository
from fdp_ingestion.status import IngestionStatusRepository, RunStatus
from fdp_shared.logging import get_logger

logger = get_logger(__name__)

_DEFAULT_BATCH_SIZE = 500


class IngestionRunner:
    """Runs a set of adapters, persisting raw records and run status.

    Streaming, bounded-memory: it consumes the adapter's async generator and
    flushes every ``batch_size`` records — it never materialises a whole source
    in memory, regardless of total size (e.g. millions of StatsBomb events).
    """

    def __init__(
        self,
        raw_repo: RawRepository,
        status_repo: IngestionStatusRepository,
        event_bus: EventBus,
        batch_size: int = _DEFAULT_BATCH_SIZE,
    ) -> None:
        self._raw_repo = raw_repo
        self._status_repo = status_repo
        self._bus = event_bus
        self._batch_size = batch_size

    async def run_source(self, adapter: SourcePort) -> int:
        """Run one adapter end-to-end. Returns records written."""

        run_id = await self._status_repo.start(adapter.name)
        log = logger.bind(source=adapter.name.value, run_id=run_id)
        log.info("ingestion_started")

        buffer: list[RawRecord] = []
        records_by_entity: dict[str, list[RawRecord]] = defaultdict(list)
        total = 0

        async def flush() -> None:
            nonlocal total, buffer
            if not buffer:
                return
            written = await self._raw_repo.upsert_many(buffer)
            total += written
            # Hand the just-written records to unification IN MEMORY on the event
            # so it maps them directly — no read-back from Mongo. source_refs is
            # kept as a lightweight id list + replay fallback.
            for entity, records in records_by_entity.items():
                await self._bus.publish(
                    RawIngested(
                        source=adapter.name,
                        entity=entity,
                        source_refs=tuple(r.source_ref for r in records),
                        records=tuple(records),
                    )
                )
            buffer = []
            records_by_entity.clear()

        try:
            async for record in adapter.fetch():
                buffer.append(record)
                records_by_entity[record.entity].append(record)
                if len(buffer) >= self._batch_size:
                    await flush()
            await flush()
        except Exception as exc:
            log.error("ingestion_failed", error=str(exc))
            await self._status_repo.finish(
                run_id,
                status=RunStatus.FAILURE,
                record_count=total,
                error_summary=f"{type(exc).__name__}: {exc}",
            )
            return total

        await self._status_repo.finish(run_id, status=RunStatus.SUCCESS, record_count=total)
        log.info("ingestion_succeeded", records=total)
        return total

    async def run_all(self, adapters: list[SourcePort]) -> dict[str, int]:
        """Run every adapter sequentially; return per-source written counts.

        Sequential (not concurrent) so each source's polite rate budget is
        respected without contention, and so a slow source cannot starve another.
        """

        results: dict[str, int] = {}
        for adapter in adapters:
            results[adapter.name.value] = await self.run_source(adapter)
        return results
