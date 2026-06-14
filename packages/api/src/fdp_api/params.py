"""Query-parameter parsing into the shared QuerySpec.

Translates the HTTP surface (``page``, ``size``, ``sort=field:asc,other:desc``,
and arbitrary ``filter[...]`` style equality params) into the persistence-
agnostic :class:`fdp_shared.query.QuerySpec`. Only fields on an allow-list per
endpoint are accepted for filter/sort, which prevents clients from probing
arbitrary document internals and keeps queries index-friendly.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Query

from fdp_shared.query import Pagination, QuerySpec, SortDir, SortField


def parse_sort(raw: str | None, allowed: set[str]) -> list[SortField]:
    """Parse ``field:dir,field2`` into SortField list, validating field names."""

    if not raw:
        return []
    fields: list[SortField] = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        name, _, direction = token.partition(":")
        if name not in allowed:
            from fdp_shared.exceptions import ValidationFailedError

            raise ValidationFailedError(f"cannot sort by {name!r}")
        fields.append(
            SortField(
                field=name,
                direction=SortDir(direction) if direction else SortDir.ASC,
            )
        )
    return fields


def build_spec(
    *,
    page: int,
    size: int,
    sort: str | None,
    filters: dict[str, Any],
    allowed_fields: set[str],
) -> QuerySpec:
    """Assemble a validated QuerySpec from raw query params."""

    clean_filters = {k: v for k, v in filters.items() if v is not None and k in allowed_fields}
    return QuerySpec(
        filters=clean_filters,
        sort=parse_sort(sort, allowed_fields),
        pagination=Pagination(page=page, size=size),
    )


# Reusable FastAPI query params for pagination/sort across all browse endpoints.
PageParam = Annotated[int, Query(ge=1, description="1-indexed page number")]
SizeParam = Annotated[int, Query(ge=1, le=200, description="Page size")]
SortParam = Annotated[
    str | None,
    Query(description="Comma-separated 'field:asc|desc' list, e.g. 'match_date:desc'"),
]
