"""Async API client used by the UI pages.

The UI shares the same ASGI process as the API, so it talks to the API over
loopback HTTP. This keeps the UI decoupled from service/repository internals —
it consumes exactly the public REST contract, the same one external clients use,
which is also what the acceptance criteria exercise.

Base URL is env-driven (``UI_API_BASE_URL``) so it can be repointed without code
changes; it defaults to the local app.
"""

from __future__ import annotations

import contextlib
import os
from typing import Any

import httpx

_BASE_URL = os.environ.get("UI_API_BASE_URL", "http://127.0.0.1:8000")


class ApiError(RuntimeError):
    """Raised when the API returns a non-2xx response (carries problem detail)."""


class ApiClient:
    def __init__(self, base_url: str | None = None) -> None:
        self._base = (base_url or _BASE_URL).rstrip("/")

    async def _request(self, method: str, path: str, **kw: Any) -> Any:
        async with httpx.AsyncClient(base_url=self._base, timeout=60.0) as client:
            resp = await client.request(method, path, **kw)
            if resp.status_code >= 400:
                detail = resp.text
                with contextlib.suppress(Exception):
                    detail = resp.json().get("detail", detail)
                raise ApiError(f"{resp.status_code}: {detail}")
            if resp.status_code == 204 or not resp.content:
                return None
            return resp.json()

    async def tools(self) -> Any:
        return await self._request("GET", "/api/tools")

    async def list_pipelines(self) -> Any:
        return await self._request("GET", "/api/pipelines")

    async def get_pipeline(self, pid: str) -> Any:
        return await self._request("GET", f"/api/pipelines/{pid}")

    async def create_pipeline(self, body: dict[str, Any]) -> Any:
        return await self._request("POST", "/api/pipelines", json=body)

    async def update_pipeline(self, pid: str, body: dict[str, Any]) -> Any:
        return await self._request("PUT", f"/api/pipelines/{pid}", json=body)

    async def delete_pipeline(self, pid: str) -> None:
        await self._request("DELETE", f"/api/pipelines/{pid}")

    async def preview(self, pid: str, limit: int = 10) -> Any:
        return await self._request("POST", f"/api/pipelines/{pid}/preview", params={"limit": limit})

    async def run(self, pid: str) -> Any:
        return await self._request("POST", f"/api/pipelines/{pid}/run", json={"error_mode": "skip"})

    async def runs(self, pipeline_id: str | None = None) -> Any:
        params = {"pipeline_id": pipeline_id} if pipeline_id else {}
        return await self._request("GET", "/api/pipeline-runs", params=params)

    async def lineage(self, target: str, target_id: str) -> Any:
        return await self._request(
            "GET", "/api/lineage", params={"target": target, "id": target_id}
        )

    async def browse_raw(self, source: str, page: int, size: int) -> Any:
        return await self._request("GET", f"/api/raw/{source}", params={"page": page, "size": size})

    async def browse_unified(self, collection: str, page: int, size: int) -> Any:
        return await self._request(
            "GET", f"/api/unified/{collection}", params={"page": page, "size": size}
        )

    async def edit_raw(self, source: str, entity: str, source_ref: str, payload: Any) -> Any:
        return await self._request(
            "PUT",
            f"/api/raw/{source}",
            json={"entity": entity, "source_ref": source_ref, "payload": payload},
        )

    async def aggregates(self, page: int, size: int) -> Any:
        return await self._request(
            "GET", "/api/aggregate/matches", params={"page": page, "size": size}
        )

    async def aggregate(self, match_id: str) -> Any:
        return await self._request("GET", f"/api/aggregate/matches/{match_id}")

    async def rebuild_aggregates(self, match_id: str | None = None) -> Any:
        params = {"match_id": match_id} if match_id else {}
        return await self._request("POST", "/api/aggregate/rebuild", params=params)


client = ApiClient()
