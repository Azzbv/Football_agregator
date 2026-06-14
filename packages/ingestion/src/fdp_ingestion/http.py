"""Polite async HTTP client wrapper.

Combines three robustness primitives — and *only* these. There is deliberately
no proxy rotation, no user-agent spoofing for evasion, no anti-detection: per
the design's explicit non-goals, robustness means rate limiting, retry, caching
and conditional requests, not evasion.

* :class:`aiolimiter.AsyncLimiter` — token-bucket rate limiting. For FBref this
  enforces the Sports Reference policy of <= 10 requests/minute with >= 6s
  spacing.
* :mod:`tenacity` — exponential backoff with jitter on transient failures.
* an in-memory conditional-request cache — stores ETag / Last-Modified per URL
  and re-sends them so unchanged resources return 304 and are served from cache.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import httpx
from aiolimiter import AsyncLimiter
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from fdp_shared.logging import get_logger

logger = get_logger(__name__)

# A descriptive, honest User-Agent. This identifies the bot rather than
# disguising it — the opposite of evasion.
USER_AGENT = "football-data-platform/0.1 (+https://example.invalid/fdp; polite-bot)"


@dataclass
class _CacheEntry:
    body: bytes
    etag: str | None
    last_modified: str | None


@dataclass
class PoliteClient:
    """A rate-limited, retrying, caching async HTTP client.

    One instance per source so each source gets its own independent rate budget
    and its own ``min_spacing`` floor. The token bucket caps the *average* rate;
    ``min_spacing`` additionally guarantees a hard minimum gap between requests,
    which is what the FBref >= 6s rule requires (a pure bucket could otherwise
    burst two requests back-to-back).
    """

    requests_per_minute: int
    min_spacing_seconds: float = 0.0
    _client: httpx.AsyncClient = field(init=False)
    _limiter: AsyncLimiter = field(init=False)
    _lock: asyncio.Lock = field(init=False, default_factory=asyncio.Lock)
    _last_request_monotonic: float = field(init=False, default=0.0)
    _cache: dict[str, _CacheEntry] = field(init=False, default_factory=dict)

    def __post_init__(self) -> None:
        self._client = httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT},
            timeout=httpx.Timeout(30.0),
            follow_redirects=True,
        )
        # Token bucket: `requests_per_minute` tokens replenished over 60s.
        self._limiter = AsyncLimiter(max_rate=self.requests_per_minute, time_period=60.0)

    async def __aenter__(self) -> PoliteClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _respect_min_spacing(self) -> None:
        """Sleep until at least ``min_spacing_seconds`` has elapsed since the
        last request. Serialised by a lock so concurrent callers can't slip
        past the floor."""

        if self.min_spacing_seconds <= 0:
            return
        async with self._lock:
            loop = asyncio.get_running_loop()
            elapsed = loop.time() - self._last_request_monotonic
            wait = self.min_spacing_seconds - elapsed
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request_monotonic = loop.time()

    @retry(
        retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
        wait=wait_exponential_jitter(initial=1, max=30),
        stop=stop_after_attempt(4),
        reraise=True,
    )
    async def get(self, url: str) -> bytes:
        """GET ``url`` with rate limiting, conditional requests and retry.

        Returns the response body. On a 304 the cached body is returned. 4xx
        (other than 429) are not retried; 429/5xx and transport errors are.
        """

        await self._limiter.acquire()
        await self._respect_min_spacing()

        headers: dict[str, str] = {}
        cached = self._cache.get(url)
        if cached:
            if cached.etag:
                headers["If-None-Match"] = cached.etag
            if cached.last_modified:
                headers["If-Modified-Since"] = cached.last_modified

        logger.debug("http_get", url=url, conditional=bool(headers))
        resp = await self._client.get(url, headers=headers)

        if resp.status_code == 304 and cached:
            logger.debug("http_304_cache_hit", url=url)
            return cached.body

        # Retry on rate-limit / server errors; let client errors surface.
        if resp.status_code == 429 or resp.status_code >= 500:
            resp.raise_for_status()
        resp.raise_for_status()

        self._cache[url] = _CacheEntry(
            body=resp.content,
            etag=resp.headers.get("ETag"),
            last_modified=resp.headers.get("Last-Modified"),
        )
        return resp.content
