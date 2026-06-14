"""Integration test: unified repository upsert + filter/sort/paginate on real Mongo.

Skipped automatically when Docker/testcontainers is unavailable (see conftest).
Proves idempotent upsert (no duplicates on re-run) and that QuerySpec drives
working filter, multi-field sort and pagination.
"""

from __future__ import annotations

from typing import Any

import pytest

from fdp_shared.domain import Match, SourceName, Team
from fdp_shared.mongo import ensure_indices
from fdp_shared.query import Pagination, QuerySpec, SortDir, SortField
from fdp_unification.repository import UnifiedRepository

pytestmark = pytest.mark.asyncio


def _match(ref: str, comp: str, score: int) -> Match:
    return Match(
        source=SourceName.STATSBOMB,
        source_ref=ref,
        match_id=f"statsbomb:{ref}",
        competition=comp,
        home_team=Team(team_id="t1", name="Home"),
        away_team=Team(team_id="t2", name="Away"),
        home_score=score,
        away_score=0,
    )


async def test_upsert_is_idempotent(db: Any) -> None:
    await ensure_indices(db)
    repo = UnifiedRepository(db, "matches", Match)

    await repo.upsert_many([_match("1", "PL", 1), _match("2", "PL", 2)])
    # Re-run with the same keys must NOT create duplicates.
    await repo.upsert_many([_match("1", "PL", 5)])

    page = await repo.query(QuerySpec(pagination=Pagination(page=1, size=50)))
    assert page.total == 2
    updated = next(m for m in page.items if m.source_ref == "1")
    assert updated.home_score == 5  # value updated in place.


async def test_filter_sort_paginate(db: Any) -> None:
    await ensure_indices(db)
    repo = UnifiedRepository(db, "matches", Match)
    await repo.upsert_many(
        [_match("a", "PL", 3), _match("b", "PL", 1), _match("c", "LL", 2)]
    )

    spec = QuerySpec(
        filters={"competition": "PL"},
        sort=[SortField(field="home_score", direction=SortDir.DESC)],
        pagination=Pagination(page=1, size=1),
    )
    page = await repo.query(spec)
    assert page.total == 2  # only PL matches.
    assert page.pages == 2
    assert page.items[0].home_score == 3  # highest first, page size 1.
