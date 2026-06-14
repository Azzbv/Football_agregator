"""Async MongoDB client management using the PyMongo Async API.

We use :class:`pymongo.AsyncMongoClient` directly (NOT Motor, which reached
end-of-life in May 2026). A single client is shared per event loop / process —
``AsyncMongoClient`` manages its own connection pool and is safe to share across
coroutines. Creating one client per request would exhaust connections, so the
composition root constructs exactly one and injects it via DI.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pymongo import ASCENDING, AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from fdp_shared.logging import get_logger

logger = get_logger(__name__)

_INDEX_PLAN: dict[str, list[list[tuple[str, int]]]] = {
    "matches": [
        [("match_id", ASCENDING)],
        [("league_id", ASCENDING), ("season_id", ASCENDING)],
        [("match_date", ASCENDING)],
    ],
    "events": [
        [("event_id", ASCENDING)],
        [("match_id", ASCENDING)],
        [("player_id", ASCENDING)],
    ],
    "players": [
        [("player_id", ASCENDING)],
    ],
    "team_stats": [
        [("team_id", ASCENDING), ("match_id", ASCENDING)],
        [("league_id", ASCENDING), ("season_id", ASCENDING)],
    ],
    "player_stats": [
        [("player_id", ASCENDING), ("match_id", ASCENDING)],
        [("league_id", ASCENDING), ("season_id", ASCENDING)],
    ],
    "ingestion_runs": [
        [("source", ASCENDING), ("started_at", ASCENDING)],
    ],
    "match_aggregates": [
        [("match_id", ASCENDING)],
        [("match.league_id", ASCENDING), ("match.season_id", ASCENDING)],
    ],
}

_UNIQUE_KEYS: dict[str, list[tuple[str, int]]] = {
    "matches": [("match_id", ASCENDING)],
    "events": [("event_id", ASCENDING)],
    "players": [("player_id", ASCENDING)],
    "team_stats": [("team_id", ASCENDING), ("match_id", ASCENDING)],
    "player_stats": [("player_id", ASCENDING), ("match_id", ASCENDING)],
    "match_aggregates": [("match_id", ASCENDING)],
}


def create_client(mongodb_uri: str) -> AsyncMongoClient[Mapping[str, Any]]:
    """Create the shared AsyncMongoClient. Connection details come only from URI."""

    logger.info("creating_mongo_client")
    return AsyncMongoClient(mongodb_uri, tz_aware=True)


async def ping(client: AsyncMongoClient[Mapping[str, Any]]) -> bool:
    """Readiness check: round-trip a ping to the server."""

    await client.admin.command("ping")
    return True


async def ensure_indices(db: AsyncDatabase[Mapping[str, Any]]) -> None:
    """Create all indices idempotently at startup.

    Unique indices encode the per-collection upsert key so duplicates are
    impossible at the storage layer, not just at the application layer.
    """

    for collection, key in _UNIQUE_KEYS.items():
        await db[collection].create_index(key, unique=True, name=f"uq_{collection}")

    for collection, indexes in _INDEX_PLAN.items():
        for keys in indexes:
            await db[collection].create_index(keys)

    logger.info("indices_ensured", collections=list(_INDEX_PLAN))
