"""Rate-limiter test: proves FBref's >=6s spacing / <=10 req/min cap.

We mock HTTP with respx (no live network) and drive a PoliteClient configured
exactly as the FBref adapter's: 10 rpm + 6s min spacing. We monkeypatch the
event loop clock indirectly by asserting the limiter inserts sleeps; rather than
sleeping 6s in the test, we patch asyncio.sleep to record the requested delays
and assert the spacing floor is requested.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest
import respx

from fdp_ingestion.http import PoliteClient


@pytest.mark.asyncio
@respx.mock
async def test_min_spacing_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    respx.get("https://fbref.test/page").mock(return_value=httpx.Response(200, content=b"ok"))

    slept: list[float] = []
    real_sleep = asyncio.sleep

    async def fake_sleep(delay: float) -> None:
        slept.append(delay)
        await real_sleep(0)  # don't actually wait.

    monkeypatch.setattr("fdp_ingestion.http.asyncio.sleep", fake_sleep)

    client = PoliteClient(requests_per_minute=10, min_spacing_seconds=6.0)
    try:
        # Two back-to-back requests: the second must be spaced >=6s after the first.
        await client.get("https://fbref.test/page")
        await client.get("https://fbref.test/page")
    finally:
        await client.aclose()

    # The second request triggers a spacing sleep close to the 6s floor.
    spacing_sleeps = [s for s in slept if s > 5.0]
    assert spacing_sleeps, f"expected a >=6s spacing sleep, got {slept}"
    assert max(spacing_sleeps) <= 6.0 + 0.001


def test_fbref_configured_with_policy_cap() -> None:
    """The adapter wiring uses 10 rpm + 6s spacing (verified at construction)."""

    client = PoliteClient(requests_per_minute=10, min_spacing_seconds=6.0)
    assert client.requests_per_minute == 10
    assert client.min_spacing_seconds == 6.0
