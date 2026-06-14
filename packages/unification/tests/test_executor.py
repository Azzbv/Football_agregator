"""Executor + lineage-capture tests.

``transform_record`` is pure (no DB), so we exercise the full step-threading and
lineage accumulation without Mongo. We also assert the source document is never
mutated and that a filter step drops the record.
"""

from __future__ import annotations

from fdp_unification.orchestration.executor import PipelineExecutor
from fdp_unification.orchestration.models import Pipeline, StepConfig


def _pipeline(steps: list[StepConfig], **kw) -> Pipeline:
    return Pipeline(
        name="t",
        source_collection="raw_understat",
        target_collection="matches",
        upsert_key=["match_id"],
        steps=steps,
        **kw,
    )


def test_transform_threads_steps_and_accumulates_lineage() -> None:
    executor = PipelineExecutor(db=None)  # type: ignore[arg-type] - transform is DB-free.
    pipeline = _pipeline(
        [
            StepConfig(type="extract", config={"source_path": "id", "target_path": "match_id"}),
            StepConfig(type="extract", config={"source_path": "h.title", "target_path": "home"}),
            StepConfig(type="concat", config={"source_paths": ["home", "a_title"], "target_path": "label", "separator": " vs "}),
            StepConfig(type="constant", config={"target_path": "source", "value": "understat"}),
            StepConfig(type="drop", config={"target_path": "h"}),
        ]
    )
    steps = executor._build_steps(pipeline)
    source = {"_id": "abc", "id": "1001", "h": {"title": "Arsenal"}, "a_title": "Chelsea"}

    output, lineage, reason = executor.transform_record(steps, source)

    assert reason is None
    assert output is not None
    assert output["match_id"] == "1001"
    assert output["home"] == "Arsenal"
    assert output["label"] == "Arsenal vs Chelsea"
    assert output["source"] == "understat"
    assert "h" not in output            # dropped
    assert "_id" not in output          # Mongo _id stripped
    # Source document untouched (deep-copied internally).
    assert source["h"] == {"title": "Arsenal"}
    # Lineage: one entry per step (concat=1, split would be many); 5 here.
    assert len(lineage) == 5
    assert {e.step_type for e in lineage} == {"extract", "concat", "constant", "drop"}
    # match_id mapping is captured for the lineage view.
    match_id_entry = next(e for e in lineage if e.target_path == "match_id")
    assert match_id_entry.source_paths == ["id"]
    assert match_id_entry.after_value == "1001"


def test_filter_step_drops_record_with_reason() -> None:
    executor = PipelineExecutor(db=None)  # type: ignore[arg-type]
    pipeline = _pipeline(
        [StepConfig(type="filter", config={"target_path": "goals", "op": "exists"})]
    )
    steps = executor._build_steps(pipeline)
    output, lineage, reason = executor.transform_record(steps, {"other": 1})
    assert output is None
    assert reason is not None
    assert lineage  # the filter still emits a lineage entry explaining the drop.


def test_invalid_step_config_raises_on_build() -> None:
    import pytest

    from fdp_shared.exceptions import ValidationFailedError

    executor = PipelineExecutor(db=None)  # type: ignore[arg-type]
    # 'cast' requires a valid 'to'; an unknown value fails Pydantic validation.
    bad = _pipeline([StepConfig(type="cast", config={"target_path": "x", "to": "banana"})])
    with pytest.raises((ValidationFailedError, ValueError)):
        executor._build_steps(bad)
