"""API response DTOs.

The API never exposes raw persistence documents. Browse endpoints return a
:class:`PageResponse` envelope wrapping the unified domain DTOs (which already
exclude Mongo internals like ``_id``) plus pagination metadata.
"""

from __future__ import annotations

from pydantic import BaseModel

from fdp_shared.query import Page


class PageResponse[T](BaseModel):
    """Paginated browse response."""

    items: list[T]
    page: int
    size: int
    total: int
    pages: int

    @classmethod
    def from_page(cls, page: Page[T]) -> PageResponse[T]:
        return cls(
            items=page.items,
            page=page.page,
            size=page.size,
            total=page.total,
            pages=page.pages,
        )
