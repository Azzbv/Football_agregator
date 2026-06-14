"""ASGI entry point.

``fdp_app.main:app`` is the importable ASGI application Uvicorn serves. It is a
module-level singleton built by the composition root so Uvicorn (and tests) can
reference it by import string.
"""

from __future__ import annotations

from fdp_app.factory import create_app

app = create_app()
