"""Integration-test DB fixture.

Provides a real MongoDB via testcontainers, accessed through the PyMongo Async
API (the same ``AsyncMongoClient`` the app uses — never Motor, which is EOL).
If Docker is unavailable the dependent tests are skipped rather than run against
a non-representative shim, so a green run always reflects real Mongo behaviour.
No live external network is used — the container is local.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio


@pytest_asyncio.fixture
async def db() -> AsyncIterator[object]:
    try:
        from pymongo import AsyncMongoClient
        from testcontainers.mongodb import MongoDbContainer
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"testcontainers/pymongo unavailable: {exc}")

    try:
        container = MongoDbContainer("mongo:7")
        container.start()
    except Exception as exc:  # noqa: BLE001 - Docker daemon not running.
        pytest.skip(f"Docker unavailable for testcontainers: {exc}")

    client: AsyncMongoClient[object] = AsyncMongoClient(container.get_connection_url())
    try:
        yield client["test"]
    finally:
        await client.close()
        container.stop()
