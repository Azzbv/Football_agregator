"""NiceGUI pages: builder, data browser/editor, lineage, dry-run, runs.

Each page is registered with ``@ui.page`` under ``/ui*`` and renders through the
shared scaffold. Data access is exclusively via :mod:`fdp_ui.client` (the REST
API), so the UI stays decoupled from service internals. Every page handles
loading/error/empty states explicitly.

The Data page consolidates raw/unified/aggregate browsing into one view with a
VS Code-like (CodeMirror) JSON editor; raw payloads are editable and saved back
through the API.
"""

from __future__ import annotations

import contextlib
import json
from typing import Any

from nicegui import ui

from fdp_ui.client import ApiError, client
from fdp_ui.forms import render_config_form
from fdp_ui.layout import page_scaffold

_RAW_SOURCES = ["statsbomb", "fbref", "openfootball", "understat"]
_UNIFIED = ["matches", "events", "players", "team_stats", "player_stats"]
_EDITOR_THEME = "vscodeDark"


async def _notify_error(exc: Exception) -> None:
    ui.notify(f"Error: {exc}", type="negative")


def _json_editor(value: Any, *, readonly: bool) -> Any:
    """A VS Code-like CodeMirror JSON editor; returns the element."""

    text = json.dumps(value, indent=2, default=str)
    editor = ui.codemirror(text, language="JSON", theme=_EDITOR_THEME).classes("w-full")
    editor.props(f"readonly={str(readonly).lower()}")
    editor.style("height: 70vh; border-radius: 6px; overflow: hidden")
    return editor


class _BuilderState:
    """Holds the in-progress pipeline being assembled in the builder."""

    def __init__(self) -> None:
        self.tools: list[dict[str, Any]] = []
        self.steps: list[dict[str, Any]] = []


def register_pages() -> None:
    @ui.page("/ui")
    async def builder_page() -> None:
        state = _BuilderState()

        def body() -> None:
            ui.label("Pipeline Builder").classes("text-xl font-medium")
            name = ui.input("Pipeline name", value="my-pipeline").classes("w-full")
            with ui.row().classes("w-full gap-4"):
                source = ui.select(
                    _RAW_SOURCES, label="Source collection (raw_*)", value="understat"
                ).classes("flex-1")
                target = ui.select(_UNIFIED, label="Target collection", value="matches").classes(
                    "flex-1"
                )
            upsert_key = ui.input("Upsert key fields (comma-separated)", value="match_id").classes(
                "w-full"
            )

            ui.separator()
            ui.label("Steps").classes("text-sm font-medium text-grey-7")
            steps_container = ui.column().classes("w-full gap-2")

            async def load_tools() -> None:
                try:
                    state.tools = await client.tools()
                    palette.options = [t["type"] for t in state.tools]
                    palette.update()
                except ApiError as exc:
                    await _notify_error(exc)

            def render_steps() -> None:
                steps_container.clear()
                if not state.steps:
                    with steps_container:
                        ui.label("No steps yet — add one from the palette.").classes("text-grey")
                for idx, step in enumerate(state.steps):
                    with steps_container, ui.card().classes("w-full").props("flat bordered"):
                        with ui.row().classes("items-center justify-between w-full"):
                            ui.label(f"{idx + 1}. {step['type']}").classes("font-medium")
                            with ui.row():
                                ui.button(
                                    icon="arrow_upward", on_click=lambda _, i=idx: move(i, -1)
                                ).props("flat dense")
                                ui.button(
                                    icon="arrow_downward", on_click=lambda _, i=idx: move(i, 1)
                                ).props("flat dense")
                                ui.button(icon="delete", on_click=lambda _, i=idx: remove(i)).props(
                                    "flat dense color=negative"
                                )
                        schema = next(
                            t["config_schema"] for t in state.tools if t["type"] == step["type"]
                        )
                        step["config_getter"] = render_config_form(schema, step.get("config"))

            def move(idx: int, delta: int) -> None:
                j = idx + delta
                if 0 <= j < len(state.steps):
                    _snapshot()
                    state.steps[idx], state.steps[j] = state.steps[j], state.steps[idx]
                    render_steps()

            def remove(idx: int) -> None:
                _snapshot()
                state.steps.pop(idx)
                render_steps()

            def _snapshot() -> None:
                for step in state.steps:
                    getter = step.get("config_getter")
                    if getter:
                        with contextlib.suppress(Exception):
                            step["config"] = getter()

            def add_step() -> None:
                if not palette.value:
                    return
                state.steps.append({"type": palette.value, "config": {}})
                render_steps()

            with ui.row().classes("items-end gap-2"):
                palette = ui.select([], label="Add step type").classes("w-64")
                ui.button("Add step", icon="add", on_click=add_step).props("flat")

            async def save() -> None:
                _snapshot()
                body_payload = {
                    "name": name.value,
                    "source_collection": f"raw_{source.value}",
                    "target_collection": target.value,
                    "upsert_key": [s.strip() for s in upsert_key.value.split(",") if s.strip()],
                    "steps": [
                        {"type": s["type"], "config": s.get("config", {})} for s in state.steps
                    ],
                }
                try:
                    created = await client.create_pipeline(body_payload)
                    ui.notify(f"Saved pipeline {created['id']}", type="positive")
                except ApiError as exc:
                    await _notify_error(exc)

            ui.separator()
            ui.button("Save pipeline", icon="save", on_click=save).props("color=primary")

            render_steps()
            ui.timer(0.1, load_tools, once=True)

        page_scaffold("Builder", body)

    @ui.page("/ui/data")
    async def data_page() -> None:
        # One consolidated browser/editor over raw, unified and aggregate data.
        state: dict[str, Any] = {"items": [], "selected": None}

        def body() -> None:
            ui.label("Data").classes("text-xl font-medium")
            with ui.row().classes("items-end gap-3 w-full"):
                mode = ui.toggle(
                    {"raw": "Raw", "unified": "Unified", "aggregate": "Aggregate"}, value="raw"
                ).props("no-caps dense")
                collection = ui.select(_RAW_SOURCES, value="statsbomb", label="Collection").classes(
                    "w-48"
                )
                size = ui.number("Limit", value=25, min=1, max=200).classes("w-24")
                ui.space()
                rebuild_btn = ui.button("Rebuild", icon="cached").props("flat dense")

            with ui.row().classes("w-full gap-4 no-wrap"):
                list_col = ui.column().classes("w-72 gap-1 shrink-0")
                editor_col = ui.column().classes("flex-1 gap-2 min-w-0")

            def sync_collection() -> None:
                if mode.value == "raw":
                    collection.options = _RAW_SOURCES
                    collection.value = _RAW_SOURCES[0]
                    collection.set_visibility(True)
                elif mode.value == "unified":
                    collection.options = _UNIFIED
                    collection.value = _UNIFIED[0]
                    collection.set_visibility(True)
                else:
                    collection.set_visibility(False)
                collection.update()
                rebuild_btn.set_visibility(mode.value == "aggregate")

            def _label_for(idx: int, item: dict[str, Any]) -> str:
                for k in ("match_id", "source_ref", "event_id", "player_id", "team_id"):
                    if item.get(k):
                        return str(item[k])
                return f"#{idx + 1}"

            def render_editor() -> None:
                editor_col.clear()
                item = state["selected"]
                if item is None:
                    with editor_col:
                        ui.label("Select a record.").classes("text-grey")
                    return
                editable = mode.value == "raw"
                with editor_col:
                    if editable:
                        editor = _json_editor(item.get("payload", item), readonly=False)
                        with ui.row().classes("gap-2"):
                            ui.button(
                                "Save", icon="save", on_click=lambda: save_raw(editor, item)
                            ).props("color=primary dense")
                            ui.label(
                                "Editing payload — a later ingestion run can overwrite this."
                            ).classes("text-xs text-grey-6 self-center")
                    else:
                        _json_editor(item, readonly=True)

            def render_list() -> None:
                list_col.clear()
                with list_col:
                    if not state["items"]:
                        ui.label("No records.").classes("text-grey text-sm")
                        return
                    for idx, item in enumerate(state["items"]):

                        def pick(_e: Any = None, it: dict[str, Any] = item) -> None:
                            state["selected"] = it
                            render_editor()

                        ui.button(_label_for(idx, item), on_click=pick).props(
                            "flat dense align=left no-caps"
                        ).classes("w-full text-grey-9")

            async def load() -> None:
                state["selected"] = None
                render_editor()
                try:
                    if mode.value == "raw":
                        data = await client.browse_raw(collection.value, 1, int(size.value))
                        state["items"] = data.get("items", [])
                    elif mode.value == "unified":
                        data = await client.browse_unified(collection.value, 1, int(size.value))
                        state["items"] = data.get("items", [])
                    else:
                        data = await client.aggregates(1, int(size.value))
                        state["items"] = data.get("items", [])
                except ApiError as exc:
                    await _notify_error(exc)
                    state["items"] = []
                render_list()

            async def save_raw(editor: Any, item: dict[str, Any]) -> None:
                try:
                    payload = json.loads(editor.value)
                except json.JSONDecodeError as exc:
                    ui.notify(f"Invalid JSON: {exc}", type="negative")
                    return
                try:
                    updated = await client.edit_raw(
                        collection.value, item["entity"], item["source_ref"], payload
                    )
                    item.update(updated)
                    ui.notify("Saved", type="positive")
                except (ApiError, KeyError) as exc:
                    await _notify_error(exc if isinstance(exc, ApiError) else ApiError(str(exc)))

            async def rebuild() -> None:
                try:
                    result = await client.rebuild_aggregates()
                    ui.notify(f"Rebuilt {result['written']} aggregate(s)", type="positive")
                    await load()
                except ApiError as exc:
                    await _notify_error(exc)

            mode.on("update:model-value", lambda _: (sync_collection(), load()))
            collection.on("update:model-value", lambda _: load())
            rebuild_btn.on("click", lambda _: rebuild())
            sync_collection()
            ui.timer(0.1, load, once=True)

        page_scaffold("Data", body)

    @ui.page("/ui/lineage")
    async def lineage_page() -> None:
        def body() -> None:
            ui.label("Mapping / Lineage").classes("text-xl font-medium")
            ui.label("Show how raw fields mapped to unified fields for one record.").classes(
                "text-grey text-sm"
            )
            with ui.row().classes("gap-2 items-end"):
                target = ui.select(_UNIFIED, value="matches", label="Target collection").classes(
                    "w-48"
                )
                target_id = ui.input("Target id (upsert key value)").classes("w-96")
                load_btn = ui.button("Load", icon="search").props("flat")
            result = ui.column().classes("w-full")

            async def load() -> None:
                result.clear()
                try:
                    doc = await client.lineage(target.value, target_id.value)
                except ApiError as exc:
                    with result:
                        ui.label(f"Error: {exc}").classes("text-negative")
                    return
                _render_lineage(result, doc)

            load_btn.on("click", lambda _: load())

        page_scaffold("Lineage", body)

    @ui.page("/ui/preview")
    async def preview_page() -> None:
        def body() -> None:
            ui.label("Dry-Run / Preview").classes("text-xl font-medium")
            ui.label("Run a saved pipeline against N sample records — no writes.").classes(
                "text-grey text-sm"
            )
            with ui.row().classes("gap-2 items-end"):
                pipeline_sel = ui.select({}, label="Pipeline").classes("w-96")
                limit = ui.number("Sample size", value=5, min=1, max=50).classes("w-32")
                run_btn = ui.button("Preview", icon="play_arrow").props("flat")
                commit_btn = ui.button("Run & Commit", icon="bolt").props("color=negative")
            result = ui.column().classes("w-full")

            async def load_pipelines() -> None:
                try:
                    pls = await client.list_pipelines()
                    pipeline_sel.options = {
                        p["id"]: f"{p['name']} ({p['source_collection']} -> {p['target_collection']})"
                        for p in pls
                    }
                    pipeline_sel.update()
                except ApiError as exc:
                    await _notify_error(exc)

            async def do_preview() -> None:
                result.clear()
                if not pipeline_sel.value:
                    ui.notify("Pick a pipeline first", type="warning")
                    return
                with result:
                    ui.spinner(size="lg")
                try:
                    items = await client.preview(pipeline_sel.value, int(limit.value))
                except ApiError as exc:
                    result.clear()
                    with result:
                        ui.label(f"Error: {exc}").classes("text-negative")
                    return
                result.clear()
                _render_preview(result, items)

            async def do_commit() -> None:
                if not pipeline_sel.value:
                    return
                try:
                    summary = await client.run(pipeline_sel.value)
                    ui.notify(
                        f"Run {summary['status']}: {summary['output_count']} written, "
                        f"{summary['skipped_count']} skipped",
                        type="positive",
                    )
                except ApiError as exc:
                    await _notify_error(exc)

            run_btn.on("click", lambda _: do_preview())
            commit_btn.on("click", lambda _: do_commit())
            ui.timer(0.1, load_pipelines, once=True)

        page_scaffold("Preview", body)

    @ui.page("/ui/runs")
    async def runs_page() -> None:
        def body() -> None:
            ui.label("Pipeline Runs").classes("text-xl font-medium")
            holder = ui.column().classes("w-full")

            async def load() -> None:
                holder.clear()
                try:
                    runs = await client.runs()
                except ApiError as exc:
                    with holder:
                        ui.label(f"Error: {exc}").classes("text-negative")
                    return
                with holder:
                    if not runs:
                        ui.label("No runs yet.").classes("text-grey")
                        return
                    columns = [
                        {"name": "status", "label": "Status", "field": "status"},
                        {"name": "input_count", "label": "Input", "field": "input_count"},
                        {"name": "output_count", "label": "Output", "field": "output_count"},
                        {"name": "skipped_count", "label": "Skipped", "field": "skipped_count"},
                        {"name": "started_at", "label": "Started", "field": "started_at"},
                    ]
                    ui.table(columns=columns, rows=runs, row_key="started_at").classes(
                        "w-full"
                    ).props("flat bordered")

            ui.timer(0.1, load, once=True)

        page_scaffold("Runs", body)


def _render_lineage(holder: Any, doc: dict[str, Any]) -> None:
    """Render the two-column field mapping + ordered before/after changes."""

    entries = doc.get("entries", [])
    with holder:
        ui.label(
            f"Source: {doc['source_collection']} -> Target: {doc['target_collection']}"
        ).classes("font-medium")
        with ui.card().classes("w-full").props("flat bordered"):
            ui.label("Field mapping (source -> target)").classes("font-medium text-sm")
            for e in entries:
                if not e.get("target_path"):
                    continue
                with ui.row().classes("items-center gap-2"):
                    ui.label(", ".join(e.get("source_paths") or ["—"])).classes(
                        "text-right w-64 text-grey-8"
                    )
                    ui.icon("arrow_forward").classes("text-grey-5")
                    ui.label(e["target_path"]).classes("w-64")
                    ui.label(f"({e['step_type']})").classes("text-xs text-grey")
        with ui.card().classes("w-full").props("flat bordered"):
            ui.label("Applied changes (ordered)").classes("font-medium text-sm")
            columns = [
                {"name": "step_type", "label": "Step", "field": "step_type"},
                {"name": "target_path", "label": "Target", "field": "target_path"},
                {"name": "before_value", "label": "Before", "field": "before_value"},
                {"name": "after_value", "label": "After", "field": "after_value"},
                {"name": "note", "label": "Note", "field": "note"},
            ]
            rows = [
                {
                    k: str(e.get(k))
                    for k in ("step_type", "target_path", "before_value", "after_value", "note")
                }
                for e in entries
            ]
            ui.table(columns=columns, rows=rows, row_key="step_type").classes("w-full").props(
                "flat bordered"
            )


def _render_preview(holder: Any, items: list[dict[str, Any]]) -> None:
    """Render input -> output side by side plus lineage per sample record."""

    with holder:
        if not items:
            ui.label("No sample records found in the source collection.").classes("text-grey")
            return
        for i, item in enumerate(items):
            with ui.expansion(
                f"Record {i + 1}" + (" — DROPPED" if item.get("dropped") else ""), icon="article"
            ).classes("w-full"):
                if item.get("dropped"):
                    ui.label(f"Dropped: {item.get('drop_reason')}").classes("text-negative")
                with ui.row().classes("w-full gap-4"):
                    with ui.column().classes("flex-1"):
                        ui.label("Input (raw)").classes("font-medium text-sm")
                        _json_editor(item.get("input", {}), readonly=True)
                    with ui.column().classes("flex-1"):
                        ui.label("Output (unified)").classes("font-medium text-sm")
                        _json_editor(item.get("output") or {}, readonly=True)
                ui.label("Lineage").classes("font-medium text-sm")
                columns = [
                    {"name": "step_type", "label": "Step", "field": "step_type"},
                    {"name": "target_path", "label": "Target", "field": "target_path"},
                    {"name": "before_value", "label": "Before", "field": "before_value"},
                    {"name": "after_value", "label": "After", "field": "after_value"},
                ]
                rows = [
                    {
                        k: str(e.get(k))
                        for k in ("step_type", "target_path", "before_value", "after_value")
                    }
                    for e in item.get("lineage", [])
                ]
                ui.table(columns=columns, rows=rows, row_key="step_type").classes("w-full")
