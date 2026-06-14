"""The SourcePort: the single contract every source adapter implements.

Hexagonal design — the batch runner depends only on this Protocol, never on a
concrete adapter. Adding a new source means writing a new class that satisfies
``SourcePort``; no change to the runner, unification, or API is required.

Each adapter ``fetch`` yields :class:`RawRecord` objects. A raw record is a
source-shaped document plus the metadata the unification ACL needs to route and
key it. Adapters declare ``extracted_fields`` to make the per-source contract
explicit — unification discards everything else.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from fdp_shared.domain import SourceName


class RawRecord(BaseModel):
    """One raw document emitted by an adapter, destined for a raw_* collection."""

    source: SourceName
    entity: str = Field(description="Logical entity type, e.g. 'matches', 'events'.")
    source_ref: str = Field(description="Native id, used to build the upsert key.")
    payload: dict[str, Any] = Field(description="The source-shaped document, verbatim.")


@runtime_checkable
class SourcePort(Protocol):
    """Contract for a data source adapter."""

    @property
    def name(self) -> SourceName:
        """The source this adapter ingests."""
        ...

    @property
    def extracted_fields(self) -> dict[str, tuple[str, ...]]:
        """Per-entity tuple of fields this adapter promises to extract.

        Documents the explicit, declared contract per the design rules.
        """
        ...

    def fetch(self) -> AsyncIterator[RawRecord]:
        """Asynchronously yield raw records. Implementations are async generators."""
        ...
