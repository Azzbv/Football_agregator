"""Unit tests for the transform steps.

Each test asserts both the data mutation AND that structured lineage is emitted
(a step that mutates without lineage is incorrect). No DB, no network.
"""

from __future__ import annotations

from fdp_unification.transform.contract import StepContext
from fdp_unification.transform.registry import registry


def _run(type_: str, config: dict, record: dict):
    step = registry.build(type_, "s1", config)
    ctx = StepContext(step_id="s1", record=record)
    result = step.apply(ctx)
    return ctx.record, result


def test_extract_dot_path() -> None:
    rec, res = _run(
        "extract", {"source_path": "h.title", "target_path": "home"}, {"h": {"title": "Arsenal"}}
    )
    assert rec["home"] == "Arsenal"
    assert res.lineage[0].source_paths == ["h.title"]
    assert res.lineage[0].after_value == "Arsenal"


def test_extract_jsonpath() -> None:
    rec, _ = _run(
        "extract",
        {"source_path": "$.players[0].name", "target_path": "first", "jsonpath": True},
        {"players": [{"name": "Saka"}, {"name": "Ødegaard"}]},
    )
    assert rec["first"] == "Saka"


def test_rename_moves_field() -> None:
    rec, res = _run("rename", {"source_path": "old", "target_path": "new"}, {"old": 5})
    assert rec == {"new": 5}
    assert res.lineage[0].note.startswith("renamed")


def test_duplicate_keeps_original() -> None:
    rec, _ = _run("duplicate", {"source_path": "a", "target_path": "b"}, {"a": 1})
    assert rec == {"a": 1, "b": 1}


def test_constant_and_default() -> None:
    rec, _ = _run("constant", {"target_path": "x", "value": "fixed"}, {})
    assert rec["x"] == "fixed"
    rec2, _ = _run("default", {"target_path": "y", "value": "fallback"}, {"y": None})
    assert rec2["y"] == "fallback"
    rec3, res3 = _run("default", {"target_path": "y", "value": "fallback"}, {"y": "already"})
    assert rec3["y"] == "already"
    assert "skipped" in res3.lineage[0].note


def test_cast_types() -> None:
    assert _run("cast", {"target_path": "n", "to": "int"}, {"n": "42"})[0]["n"] == 42
    assert _run("cast", {"target_path": "n", "to": "float"}, {"n": "1.5"})[0]["n"] == 1.5
    assert _run("cast", {"target_path": "b", "to": "bool"}, {"b": "yes"})[0]["b"] is True


def test_trim_strips_quotes() -> None:
    rec, _ = _run("trim", {"target_path": "s"}, {"s": '  "hello"  '})
    assert rec["s"] == "hello"


def test_lookup_maps_value() -> None:
    rec, res = _run(
        "lookup",
        {"source_path": "league", "target_path": "league_id", "table": {"EPL": "PL1"}},
        {"league": "EPL"},
    )
    assert rec["league_id"] == "PL1"
    assert res.lineage[0].note == "lookup matched"


def test_concat_and_split() -> None:
    rec, _ = _run(
        "concat",
        {"source_paths": ["a", "b"], "target_path": "full", "separator": " "},
        {"a": "John", "b": "Doe"},
    )
    assert rec["full"] == "John Doe"
    rec2, res2 = _run(
        "split", {"source_path": "full", "target_paths": ["first", "last"]}, {"full": "John Doe"}
    )
    assert rec2["first"] == "John" and rec2["last"] == "Doe"
    assert len(res2.lineage) == 2


def test_drop_removes_field() -> None:
    rec, res = _run("drop", {"target_path": "secret"}, {"secret": 1, "keep": 2})
    assert rec == {"keep": 2}
    assert res.lineage[0].before_value == 1


def test_filter_keep_if_drops_record() -> None:
    _, res = _run(
        "filter", {"target_path": "score", "op": "gt", "value": 0, "mode": "keep_if"}, {"score": 0}
    )
    assert res.dropped is True
    assert res.drop_reason and "dropped" in res.drop_reason
    _, res2 = _run(
        "filter", {"target_path": "score", "op": "gt", "value": 0, "mode": "keep_if"}, {"score": 3}
    )
    assert res2.dropped is False


def test_every_step_emits_lineage() -> None:
    """No built-in step may mutate without emitting at least one lineage entry."""

    samples = {
        "extract": ({"source_path": "a", "target_path": "b"}, {"a": 1}),
        "rename": ({"source_path": "a", "target_path": "b"}, {"a": 1}),
        "duplicate": ({"source_path": "a", "target_path": "b"}, {"a": 1}),
        "constant": ({"target_path": "b", "value": 1}, {}),
        "default": ({"target_path": "b", "value": 1}, {}),
        "cast": ({"target_path": "a", "to": "str"}, {"a": 1}),
        "trim": ({"target_path": "a"}, {"a": " x "}),
        "lookup": ({"source_path": "a", "target_path": "b", "table": {}}, {"a": "x"}),
        "concat": ({"source_paths": ["a"], "target_path": "b"}, {"a": "x"}),
        "split": ({"source_path": "a", "target_paths": ["b"]}, {"a": "x"}),
        "drop": ({"target_path": "a"}, {"a": 1}),
        "filter": ({"target_path": "a", "op": "exists"}, {"a": 1}),
    }
    for type_, (config, record) in samples.items():
        _, res = _run(type_, config, record)
        assert res.lineage, f"step {type_} emitted no lineage"
