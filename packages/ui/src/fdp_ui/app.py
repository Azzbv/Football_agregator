"""Mount the NiceGUI UI onto the existing FastAPI app.

``ui.run_with(app)`` attaches NiceGUI's ASGI sub-app to the *same* FastAPI
instance, so API (``/api/*``) and UI (``/ui*``) are served by one Uvicorn process
in one container — preserving the single-entry-point requirement. We do NOT call
``ui.run`` (that would start a second server).
"""

from __future__ import annotations

from fastapi import FastAPI
from nicegui import ui

from fdp_ui.pages import register_pages


def mount_ui(app: FastAPI) -> None:
    """Register pages and bind NiceGUI to ``app``."""

    register_pages()

    @ui.page("/")
    def _root() -> None:
        ui.navigate.to("/ui")

    # storage_secret is required by NiceGUI for per-client state; env-driven, no
    # secret baked into source (falls back to a dev-only default).
    import os

    ui.run_with(
        app,
        title="Football Data Platform",
        storage_secret=os.environ.get("UI_STORAGE_SECRET", "dev-only-not-secret"),
        mount_path="/",
    )
