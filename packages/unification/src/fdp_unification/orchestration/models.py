"""Declarative pipeline definitions and run/lineage records (Pydantic v2).

A pipeline is *data*, not code: a name, a source and target collection, an
ordered list of step configs, and an upsert key. Storing it declaratively means
the UI can build/edit it, it round-trips through MongoDB, and the executor is a
generic interpreter — adding a step type never touches the executor.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from fdp_unification.transform.contract import LineageEntry


def _new_id() -> str:
    return uuid4().hex


class StepConfig(BaseModel):
    """One step in a pipeline: its id, type, and raw (unvalidated-here) config.

    The config dict is validated against the step's Pydantic model when the
    executor builds the step via the registry, so an invalid config surfaces as
    a clear error at build/preview time.
    """

    id: str = Field(default_factory=_new_id)
    type: str
    config: dict[str, Any] = Field(default_factory=dict)


class Pipeline(BaseModel):
    """A stored pipeline definition."""

    id: str = Field(default_factory=_new_id)
    name: str
    source_collection: str
    target_collection: str
    steps: list[StepConfig] = Field(default_factory=list)
    upsert_key: list[str] = Field(
        default_factory=list,
        description="Target field(s) forming the unique upsert key.",
    )
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ErrorMode(StrEnum):
    SKIP = "skip"  # skip-and-record
    FAIL_FAST = "fail_fast"


class RunStatus(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"


class RecordError(BaseModel):
    source_id: str | None = None
    message: str


class PipelineRun(BaseModel):
    """A persisted record of one commit run."""

    id: str = Field(default_factory=_new_id)
    pipeline_id: str
    status: RunStatus
    started_at: datetime
    finished_at: datetime | None = None
    input_count: int = 0
    output_count: int = 0
    skipped_count: int = 0
    errors: list[RecordError] = Field(default_factory=list)


class PreviewItem(BaseModel):
    """One dry-run result: input -> output plus the lineage that links them."""

    source_id: str | None = None
    input: dict[str, Any]
    output: dict[str, Any] | None
    dropped: bool = False
    drop_reason: str | None = None
    lineage: list[LineageEntry] = Field(default_factory=list)


class LineageDoc(BaseModel):
    """Per-unified-record lineage, stored in the dedicated ``lineage`` collection."""

    id: str = Field(default_factory=_new_id)
    target_collection: str
    target_id: str
    source_collection: str
    source_id: str | None = None
    pipeline_id: str
    run_id: str
    entries: list[LineageEntry] = Field(default_factory=list)
