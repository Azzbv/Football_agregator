"""The PipelineExecutor: a generic interpreter for declarative pipelines.

Per source record it builds the steps from the registry (validating each config),
threads a mutable working record through them in order, and accumulates lineage.
It supports two modes:

* **preview / dry-run** — run against N sample records and return input, output
  and per-record lineage WITHOUT any writes (the UI preview uses this);
* **commit** — upsert results into the target collection by the pipeline's
  ``upsert_key``, persist a per-record lineage doc, and record run status.

Per-record errors are handled per ``ErrorMode`` (skip-and-record vs fail-fast),
and transient Mongo errors are retried with tenacity backoff.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from pymongo import UpdateOne
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import AutoReconnect, ConnectionFailure, NetworkTimeout
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from fdp_shared.logging import get_logger
from fdp_unification.orchestration.models import (
    ErrorMode,
    LineageDoc,
    Pipeline,
    PipelineRun,
    PreviewItem,
    RecordError,
    RunStatus,
)
from fdp_unification.transform.contract import LineageEntry, StepContext, TransformStep
from fdp_unification.transform.paths import get_path
from fdp_unification.transform.registry import StepRegistry, registry

logger = get_logger(__name__)

_TRANSIENT = (AutoReconnect, ConnectionFailure, NetworkTimeout)


class PipelineExecutor:
    """Loads a pipeline definition and runs raw -> unified records."""

    def __init__(
        self,
        db: AsyncDatabase[Mapping[str, Any]],
        step_registry: StepRegistry | None = None,
    ) -> None:
        self._db = db
        self._registry = step_registry or registry

    # ---- step building --------------------------------------------------- #

    def _build_steps(self, pipeline: Pipeline) -> list[TransformStep]:
        """Construct + validate all steps once per run (fails fast on bad config)."""

        return [self._registry.build(sc.type, sc.id, sc.config) for sc in pipeline.steps]

    # ---- single-record transform ----------------------------------------- #

    def transform_record(
        self, steps: list[TransformStep], source_record: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, list[LineageEntry], str | None]:
        """Run all steps over one record.

        Returns ``(output_or_None_if_dropped, lineage, drop_reason)``. The input
        is deep-copied so the source document is never mutated.
        """

        working = copy.deepcopy(source_record)
        working.pop("_id", None)  # never carry Mongo's _id into the unified doc.
        lineage: list[LineageEntry] = []

        for step in steps:
            # model_construct bypasses Pydantic's copy-on-validate so the step
            # mutates *this* working dict in place (a validated StepContext would
            # receive a copy, silently discarding mutations).
            ctx = StepContext.model_construct(step_id=step.step_id, record=working)
            result = step.apply(ctx)
            working = ctx.record  # defensive: honour a step that replaced record.
            lineage.extend(result.lineage)
            if result.dropped:
                return None, lineage, result.drop_reason
        return working, lineage, None

    # ---- preview / dry-run ------------------------------------------------ #

    async def preview(self, pipeline: Pipeline, limit: int = 10) -> list[PreviewItem]:
        """Run against ``limit`` sample records WITHOUT writing anything."""

        steps = self._build_steps(pipeline)
        items: list[PreviewItem] = []
        cursor = self._db[pipeline.source_collection].find().limit(limit)
        async for raw in cursor:
            doc = dict(raw)  # Mongo yields a Mapping; we need a mutable dict.
            source_id = str(doc.get("_id")) if doc.get("_id") is not None else None
            input_copy = copy.deepcopy(doc)
            input_copy.pop("_id", None)
            output, lineage, reason = self.transform_record(steps, doc)
            items.append(
                PreviewItem(
                    source_id=source_id,
                    input=input_copy,
                    output=output,
                    dropped=output is None,
                    drop_reason=reason,
                    lineage=lineage,
                )
            )
        return items

    # ---- commit run ------------------------------------------------------- #

    def _upsert_filter(self, pipeline: Pipeline, record: dict[str, Any]) -> dict[str, Any]:
        """Build the upsert match filter from the configured key fields."""

        if not pipeline.upsert_key:
            # No key configured: fall back to a deterministic-ish identity so we
            # still upsert rather than blindly insert duplicates.
            return {"_pipeline_synthetic_key": str(sorted(record.items()))}
        return {k: get_path(record, k) for k in pipeline.upsert_key}

    @retry(
        retry=retry_if_exception_type(_TRANSIENT),
        wait=wait_exponential_jitter(initial=0.5, max=10),
        stop=stop_after_attempt(4),
        reraise=True,
    )
    async def _write_batch(self, target: str, ops: list[UpdateOne]) -> None:
        if ops:
            await self._db[target].bulk_write(ops, ordered=False)

    async def run(
        self,
        pipeline: Pipeline,
        *,
        error_mode: ErrorMode = ErrorMode.SKIP,
        run_id: str | None = None,
    ) -> PipelineRun:
        """Execute the pipeline and upsert results; persist lineage + run status."""

        steps = self._build_steps(pipeline)
        run = PipelineRun(
            pipeline_id=pipeline.id,
            status=RunStatus.SUCCESS,
            started_at=datetime.now(UTC),
        )
        if run_id:
            run.id = run_id

        write_ops: list[UpdateOne] = []
        lineage_ops: list[UpdateOne] = []
        cursor = self._db[pipeline.source_collection].find()

        async for raw in cursor:
            doc = dict(raw)  # Mongo yields a Mapping; we need a mutable dict.
            run.input_count += 1
            source_id = str(doc.get("_id")) if doc.get("_id") is not None else None
            try:
                output, lineage, reason = self.transform_record(steps, doc)
            except Exception as exc:
                run.errors.append(RecordError(source_id=source_id, message=str(exc)))
                if error_mode is ErrorMode.FAIL_FAST:
                    run.status = RunStatus.FAILURE
                    run.finished_at = datetime.now(UTC)
                    return run
                continue

            if output is None:
                run.skipped_count += 1
                logger.debug("record_dropped", source_id=source_id, reason=reason)
                continue

            match_filter = self._upsert_filter(pipeline, output)
            write_ops.append(UpdateOne(match_filter, {"$set": output}, upsert=True))
            run.output_count += 1

            # Lineage keyed by the same target identity so the UI can fetch it.
            target_id = "|".join(str(v) for v in match_filter.values())
            lineage_doc = LineageDoc(
                target_collection=pipeline.target_collection,
                target_id=target_id,
                source_collection=pipeline.source_collection,
                source_id=source_id,
                pipeline_id=pipeline.id,
                run_id=run.id,
                entries=lineage,
            )
            lineage_ops.append(
                UpdateOne(
                    {
                        "target_collection": pipeline.target_collection,
                        "target_id": target_id,
                    },
                    {"$set": lineage_doc.model_dump(mode="json")},
                    upsert=True,
                )
            )

        try:
            await self._write_batch(pipeline.target_collection, write_ops)
            await self._write_batch("lineage", lineage_ops)
        except Exception as exc:
            run.errors.append(RecordError(message=f"write failed: {exc}"))
            run.status = RunStatus.FAILURE

        if run.errors and run.status is RunStatus.SUCCESS:
            run.status = RunStatus.PARTIAL
        run.finished_at = datetime.now(UTC)
        return run
