"""Shared page layout: a minimal header + nav drawer, used by every page."""

from __future__ import annotations

from collections.abc import Callable

from nicegui import context, ui

from fdp_ui.style import INK, MUTED, apply_theme

_NAV = [
    ("Data", "/ui/data", "table_view"),
    ("Pipeline Builder", "/ui", "build"),
    ("Mapping / Lineage", "/ui/lineage", "account_tree"),
    ("Dry-Run / Preview", "/ui/preview", "play_arrow"),
    ("Runs", "/ui/runs", "history"),
]


def page_scaffold(title: str, body: Callable[[], None]) -> None:
    """Render the common header + nav, then call ``body`` for page content."""

    apply_theme()
    current = context.client.page.path if context.client.page else ""
    with ui.header().classes("fdp-header items-center gap-3"):
        ui.label("Football Data Platform").classes("text-base font-medium").style(
            f"color:{INK}"
        )
        ui.space()
        ui.label(title).classes("text-sm").style(f"color:{MUTED}")
    with ui.left_drawer().classes("fdp-drawer").props("width=220 bordered"):
        for label, path, icon in _NAV:
            active = "fdp-nav-active" if path == current else ""
            with ui.link(target=path).classes(f"fdp-nav-link {active} w-full"):
                ui.icon(icon)
                ui.label(label)
    with ui.column().classes("w-full max-w-screen-lg mx-auto p-6 gap-4"):
        body()
