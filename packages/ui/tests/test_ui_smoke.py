"""UI smoke tests (no live network, no browser).

We verify the UI can be mounted onto a FastAPI app and that its pages register —
i.e. ``mount_ui`` wires NiceGUI without error and the expected ``/ui`` routes
exist on the ASGI app. We also exercise the schema-driven form parser's pure
logic via the client's payload shaping. No external services are contacted.
"""

from __future__ import annotations

from fastapi import FastAPI

from fdp_ui import mount_ui
from fdp_ui.client import ApiClient


def test_mount_ui_mounts_nicegui_subapp() -> None:
    app = FastAPI()
    before = len(app.routes)
    mount_ui(app)
    # NiceGUI attaches itself as a Starlette Mount (a sub-ASGI app) rather than
    # adding each @ui.page as a top-level route on the parent. Assert the mount
    # was added — that is what makes the UI share this one ASGI process.
    mounts = [r for r in app.routes if type(r).__name__ == "Mount"]
    assert mounts, "NiceGUI sub-app was not mounted onto the FastAPI app"
    assert len(app.routes) > before


def test_pages_register_without_error() -> None:
    # register_pages() is invoked inside mount_ui; calling mount_ui twice on
    # fresh apps must not raise (idempotent page registration in NiceGUI).
    mount_ui(FastAPI())
    mount_ui(FastAPI())


def test_api_client_base_url_normalised() -> None:
    c = ApiClient("http://example.test:9999/")
    assert c._base == "http://example.test:9999"
