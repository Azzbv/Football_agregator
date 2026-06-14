"""Schema-driven config form renderer.

Given a step type's JSON schema (from ``GET /api/tools``), build NiceGUI inputs
dynamically and return a getter that collects the current values into a config
dict. Because the form is generated from the schema, a newly-registered step type
gets a working config form with zero UI code changes — the acceptance criterion
for extensibility.

Supported JSON-schema shapes (sufficient for the built-in steps): string,
integer, number, boolean, enum (-> select), array of strings (-> chips/textarea),
and free-form object/any (-> JSON textarea).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from nicegui import ui


def _resolve(schema: dict[str, Any], prop: dict[str, Any]) -> dict[str, Any]:
    """Resolve a property schema, following a single ``$ref`` into ``$defs``."""

    if "$ref" in prop:
        ref = prop["$ref"].split("/")[-1]
        resolved: dict[str, Any] = schema.get("$defs", {}).get(ref, {})
        return resolved
    # anyOf with a concrete type + null (Optional[...]).
    if "anyOf" in prop:
        for option in prop["anyOf"]:
            if option.get("type") != "null":
                return {**option, "title": prop.get("title", option.get("title", ""))}
    return prop


# --- typed getter factories (avoid default-capture lambdas mypy can't infer) -


def _raw_getter(el: Any) -> Callable[[], Any]:
    return lambda: el.value


def _str_getter(el: Any) -> Callable[[], Any]:
    return lambda: el.value or None


def _num_getter(el: Any, conv: Callable[[Any], Any]) -> Callable[[], Any]:
    return lambda: conv(el.value) if el.value is not None else None


def _array_getter(el: Any) -> Callable[[], list[str]]:
    return lambda: [s.strip() for s in el.value.split(",") if s.strip()]


def _json_getter(el: Any) -> Callable[[], Any]:
    def _get() -> Any:
        raw = (el.value or "").strip()
        return json.loads(raw) if raw else None

    return _get


def render_config_form(
    schema: dict[str, Any], initial: dict[str, Any] | None = None
) -> Callable[[], dict[str, Any]]:
    """Render inputs for ``schema``'s properties; return a value collector.

    ``initial`` pre-fills the inputs (used when editing an existing step).
    """

    initial = initial or {}
    properties: dict[str, Any] = schema.get("properties", {})
    required = set(schema.get("required", []))
    getters: dict[str, Callable[[], Any]] = {}

    for name, raw_prop in properties.items():
        prop = _resolve(schema, raw_prop)
        label = f"{name}{' *' if name in required else ''}"
        default = initial.get(name, raw_prop.get("default"))
        enum = prop.get("enum")
        jtype = prop.get("type")
        # NiceGUI elements are heterogeneous types; treat the handle as Any so a
        # single name can hold whichever input we render per branch.
        el: Any

        if enum:
            el = ui.select(list(enum), label=label, value=default if default in enum else enum[0])
            getters[name] = _raw_getter(el)
        elif jtype == "boolean":
            el = ui.switch(label, value=bool(default))
            getters[name] = _raw_getter(el)
        elif jtype == "integer":
            el = ui.number(label, value=default, format="%d")
            getters[name] = _num_getter(el, int)
        elif jtype == "number":
            el = ui.number(label, value=default)
            getters[name] = _num_getter(el, float)
        elif jtype == "array":
            # Comma-separated entry for arrays of scalars.
            text = ", ".join(str(x) for x in default) if isinstance(default, list) else ""
            el = ui.input(f"{label} (comma-separated)", value=text)
            getters[name] = _array_getter(el)
        elif jtype == "object" or jtype is None:
            # Free-form object / Any -> JSON textarea.
            text = json.dumps(default) if default not in (None, {}) else ""
            el = ui.textarea(f"{label} (JSON)", value=text)
            getters[name] = _json_getter(el)
        else:  # string
            el = ui.input(label, value="" if default is None else str(default))
            getters[name] = _str_getter(el)
        el.classes("w-full")

    def collect() -> dict[str, Any]:
        out: dict[str, Any] = {}
        for name, getter in getters.items():
            value = getter()
            if value is not None and value != "":
                out[name] = value
        return out

    return collect
