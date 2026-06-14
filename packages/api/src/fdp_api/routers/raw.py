"""Raw browse endpoint.

GET /api/raw/{source}/{entity} returns the raw, source-shaped documents for a
source, with pagination/filter/sort. The payload is returned verbatim under a
DTO envelope (we still never leak Mongo ``_id``). ``source`` is validated against
the SourceName enum so unknown sources yield a 400 problem+json.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from fdp_api import dependencies as deps
from fdp_api.params import PageParam, SizeParam, SortParam, parse_sort
from fdp_api.schemas import PageResponse
from fdp_ingestion.raw_repository import RawRepository
from fdp_shared.domain import SourceName
from fdp_shared.exceptions import ValidationFailedError

router = APIRouter(prefix="/api/raw", tags=["raw"])


class RawDocument(BaseModel):
    """Envelope for a raw, source-shaped document."""

    source: str
    entity: str
    source_ref: str
    payload: dict[str, Any]


@router.get("/{source}/{entity}", response_model=PageResponse[RawDocument])
async def list_raw(
    source: str,
    entity: str,
    repo: Annotated[RawRepository, Depends(deps.get_raw_repository)],
    page: PageParam = 1,
    size: SizeParam = 20,
    sort: SortParam = None,
    source_ref: Annotated[str | None, Query()] = None,
) -> PageResponse[RawDocument]:
    try:
        source_enum = SourceName(source)
    except ValueError as exc:
        raise ValidationFailedError(f"unknown source {source!r}") from exc

    sort_fields = [s.to_mongo() for s in parse_sort(sort, {"source_ref", "fetched_at", "entity"})]
    skip = (page - 1) * size
    docs, total = await repo.find(
        source_enum,
        entity if entity != "all" else None,
        skip=skip,
        limit=size,
        sort=sort_fields,
    )
    items = [
        RawDocument(
            source=source,
            entity=d["entity"],
            source_ref=d["source_ref"],
            payload=d.get("payload", {}),
        )
        for d in docs
        if source_ref is None or d["source_ref"] == source_ref
    ]
    pages = (total + size - 1) // size if size else 0
    return PageResponse(items=items, page=page, size=size, total=total, pages=pages)
