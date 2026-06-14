"""Upsert-key derivation strategy.

Every unified document needs a deterministic identity so that re-unifying the
same raw record always lands on the same unified document (idempotent upsert,
no duplicates). The rule is uniform and source-aware:

    unified_id = f"{source}:{source_ref}"

Because ``source_ref`` is the source's own native id (or, where the source has
no id — e.g. openfootball matches — a synthesised stable composite), prefixing
with the source name guarantees global uniqueness across sources while keeping
the mapping reversible for provenance. The unique index on the unified
collection (see shared.mongo._UNIQUE_KEYS) enforces this at the storage layer.
"""

from __future__ import annotations

from fdp_shared.domain import SourceName


def unified_id(source: SourceName, source_ref: str) -> str:
    """Build the deterministic unified id from provenance."""

    return f"{source.value}:{source_ref}"
