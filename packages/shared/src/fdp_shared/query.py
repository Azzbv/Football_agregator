"""Shared query primitives: pagination, multi-field sort, filter specs.

These are persistence-agnostic value objects used by the API layer to express
"give me page N, sorted by X then Y, filtered by Z" and translated by the
repository layer into Mongo find arguments. Keeping them here avoids the API
package importing repository internals or vice-versa.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class SortDir(StrEnum):
    ASC = "asc"
    DESC = "desc"


class SortField(BaseModel):
    field: str
    direction: SortDir = SortDir.ASC

    def to_mongo(self) -> tuple[str, int]:
        return (self.field, 1 if self.direction is SortDir.ASC else -1)


class Pagination(BaseModel):
    """1-indexed page pagination."""

    page: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1, le=200)

    @property
    def skip(self) -> int:
        return (self.page - 1) * self.size

    @property
    def limit(self) -> int:
        return self.size


class QuerySpec(BaseModel):
    """A complete read query: equality filters + sort + pagination."""

    filters: dict[str, Any] = Field(default_factory=dict)
    sort: list[SortField] = Field(default_factory=list)
    pagination: Pagination = Field(default_factory=Pagination)

    def mongo_sort(self) -> list[tuple[str, int]]:
        return [s.to_mongo() for s in self.sort]


class Page[T](BaseModel):
    """A page of results plus the metadata clients need to paginate."""

    items: list[T]
    page: int
    size: int
    total: int

    @property
    def pages(self) -> int:
        return (self.total + self.size - 1) // self.size if self.size else 0
