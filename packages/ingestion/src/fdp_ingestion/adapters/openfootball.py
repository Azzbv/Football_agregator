"""openfootball adapter.

openfootball publishes structured JSON/CSV/txt across many GitHub repos (one per
region/season, e.g. ``england`` -> ``2023-24/en.1.json``). We fetch the JSON
"clubs + matches" files directly — no HTML parsing. The JSON shape is::

    {"name": "...", "matches": [{"date","team1","team2","score":{"ft":[h,a]}}]}

A match has no native id in openfootball, so we synthesise a stable
``source_ref`` from date + both team names; the unification layer turns that into
the unified ``match_id``.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from fdp_shared.domain import SourceName
from fdp_shared.logging import get_logger

from fdp_ingestion.http import PoliteClient
from fdp_ingestion.ports import RawRecord

logger = get_logger(__name__)


def _slug(value: str) -> str:
    return value.strip().lower().replace(" ", "-")


@dataclass
class OpenFootballAdapter:
    """File-fetch adapter for openfootball JSON datasets."""

    base_url: str
    client: PoliteClient
    # (repo, path) pairs to fetch. Defaults to a small, well-known sample so the
    # foundation run is bounded; override via config/env for wider coverage.
    datasets: list[tuple[str, str]] = field(
        default_factory=lambda: [
            ("england", "2023-24/en.1.json"),
            ("deutschland", "2023-24/de.1.json"),
        ]
    )

    @property
    def name(self) -> SourceName:
        return SourceName.OPENFOOTBALL

    @property
    def extracted_fields(self) -> dict[str, tuple[str, ...]]:
        return {"matches": ("date", "team1", "team2", "score", "league", "season")}

    async def fetch(self) -> AsyncIterator[RawRecord]:
        for repo, path in self.datasets:
            url = f"{self.base_url}/{repo}/master/{path}"
            try:
                body = await self.client.get(url)
            except Exception as exc:  # noqa: BLE001 - one missing dataset must not abort the rest.
                logger.warning("openfootball_dataset_skipped", url=url, error=str(exc))
                continue

            doc = json.loads(body)
            league = doc.get("name", repo)
            season = path.split("/")[0]
            for match in doc.get("matches", []):
                ref = f"{match.get('date', '')}:{_slug(match['team1'])}:{_slug(match['team2'])}"
                enriched = {**match, "league": league, "season": season}
                yield RawRecord(
                    source=self.name,
                    entity="matches",
                    source_ref=ref,
                    payload=enriched,
                )
