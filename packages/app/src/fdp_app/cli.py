"""The single console script (``fdp``).

Boots the whole stack via Uvicorn. Host/port/log-level come from env so no
runtime detail is hard-coded. This is the entry point Docker/compose runs.
"""

from __future__ import annotations

import os

import uvicorn

from fdp_shared.config import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "fdp_app.main:app",
        host=os.environ.get("APP_HOST", "0.0.0.0"),  # noqa: S104 - container binds all ifaces.
        port=int(os.environ.get("APP_PORT", "8000")),
        log_level=settings.log_level.lower(),
        # Single worker keeps one shared AsyncMongoClient per process/event loop.
        workers=1,
    )


if __name__ == "__main__":
    main()
