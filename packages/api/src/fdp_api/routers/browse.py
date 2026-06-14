"""Generic paginated browse over raw and unified collections.

These complement the typed prompt-1 endpoints: the UI's Raw/Unified preview
tables need to browse *any* configured collection generically (returning the
documents as JSON), with pagination, sort, and ad-hoc equality filtering. Both
``source``/``collection`` are validated against allow-lists so arbitrary
collection names can't be probed.

``GET /api/raw/{source}``        -> raw_{source}
``GET /api/unified/{collection}`` -> the named unified collection
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Annotated, Any

from fastapi import APIRouter, Query
from pydantic import BaseModel
from pymongo.asynchronous.database import AsyncDatabase

from fdp_api import dependencies as deps
from fdp_api.params import PageParam, SizeParam, SortParam, parse_sort
from fdp_ingestion.raw_repository import RawRepository
from fdp_shared.domain import SourceName
from fdp_shared.exceptions import NotFoundError, ValidationFailedError

router = APIRouter(prefix="/api", tags=["browse"])

_UNIFIED = {"matches", "events", "players", "team_stats", "player_stats"}
_SORTABLE = {"match_id", "player_id", "team_id", "match_date", "source", "source_ref"}


class DocPage(BaseModel):
    """A page of raw JSON documents (Mongo ``_id`` stripped)."""

    items: list[dict[str, Any]]
    page: int
    size: int
    total: int
    pages: int


class RawPayloadEdit(BaseModel):
    """Body for editing a single raw document's payload."""

    entity: str
    source_ref: str
    payload: Any


def _parse_filter(raw: str | None) -> dict[str, Any]:
    """Parse an optional JSON ``filter`` query param into a Mongo equality dict."""

    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValidationFailedError(f"filter must be valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValidationFailedError("filter must be a JSON object")
    return parsed


async def _browse(
    db: AsyncDatabase[Mapping[str, Any]],
    collection: str,
    page: int,
    size: int,
    sort: str | None,
    filt: str | None,
) -> DocPage:
    col = db[collection]
    query = _parse_filter(filt)
    total = await col.count_documents(query)
    cursor = col.find(query, {"_id": 0})
    sort_fields = [s.to_mongo() for s in parse_sort(sort, _SORTABLE)]
    if sort_fields:
        cursor = cursor.sort(sort_fields)
    cursor = cursor.skip((page - 1) * size).limit(size)
    items = [dict(doc) async for doc in cursor]
    return DocPage(
        items=items,
        page=page,
        size=size,
        total=total,
        pages=(total + size - 1) // size if size else 0,
    )


@router.get("/raw/{source}", response_model=DocPage)
async def browse_raw(
    db: deps.DbDep,
    source: str,
    page: PageParam = 1,
    size: SizeParam = 20,
    sort: SortParam = None,
    filter: Annotated[str | None, Query(description="JSON equality filter")] = None,
) -> DocPage:
    try:
        SourceName(source)
    except ValueError as exc:
        raise ValidationFailedError(f"unknown source {source!r}") from exc
    return await _browse(db, f"raw_{source}", page, size, sort, filter)


@router.get("/unified/{collection}", response_model=DocPage)
async def browse_unified(
    db: deps.DbDep,
    collection: str,
    page: PageParam = 1,
    size: SizeParam = 20,
    sort: SortParam = None,
    filter: Annotated[str | None, Query(description="JSON equality filter")] = None,
) -> DocPage:
    if collection not in _UNIFIED:
        raise ValidationFailedError(f"unknown unified collection {collection!r}")
    return await _browse(db, collection, page, size, sort, filter)


@router.put("/raw/{source}", response_model=dict[str, Any])
async def edit_raw(
    db: deps.DbDep,
    source: str,
    body: RawPayloadEdit,
) -> dict[str, Any]:
    """Replace one raw document's payload, addressed by (entity, source_ref).

    Only the payload is editable; the natural key is immutable. Note a later
    ingestion run for the same key will overwrite the edit.
    """

    try:
        src = SourceName(source)
    except ValueError as exc:
        raise ValidationFailedError(f"unknown source {source!r}") from exc
    updated = await RawRepository(db).replace_payload(
        src, body.entity, body.source_ref, body.payload
    )
    if updated is None:
        raise NotFoundError(
            f"no raw {source} doc with entity={body.entity!r} source_ref={body.source_ref!r}"
        )
    return updated
