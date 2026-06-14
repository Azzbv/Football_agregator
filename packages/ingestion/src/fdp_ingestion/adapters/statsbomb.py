"""StatsBomb open-data adapter.

StatsBomb publishes structured JSON in a public GitHub repo. There is NO HTML
here — we fetch JSON files directly over HTTP. The repo layout is::

    data/competitions.json
    data/matches/{competition_id}/{season_id}.json
    data/events/{match_id}.json

We walk competitions -> matches -> events. To stay polite and bounded we cap how
many competitions/matches we descend into (configurable); a full crawl of all
open data is enormous and not the point of the foundation layer.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from fdp_ingestion.http import PoliteClient
from fdp_ingestion.ports import RawRecord
from fdp_shared.domain import SourceName
from fdp_shared.logging import get_logger

logger = get_logger(__name__)


@dataclass
class StatsBombAdapter:
    """File-fetch adapter for StatsBomb open data.

    If ``competitions`` is given (a list of ``(competition_id, season_id)``
    pairs), only those competition-seasons are ingested — this is how the top-5
    European leagues are selected. If it's empty, the adapter falls back to a
    bounded blind crawl of the first ``max_competitions`` entries in
    ``competitions.json``.

    ``include_events`` gates the (very large) per-match event files; set it to
    ``False`` to ingest matches only, which keeps a multi-league run fast and
    small. ``max_matches_per_competition = 0`` means "all matches in the season".
    """

    base_url: str
    client: PoliteClient
    competitions: list[tuple[int, int]] = field(default_factory=list)
    max_competitions: int = 2
    max_matches_per_competition: int = 5
    include_events: bool = True

    @property
    def name(self) -> SourceName:
        return SourceName.STATSBOMB

    @property
    def extracted_fields(self) -> dict[str, tuple[str, ...]]:
        return {
            "matches": (
                "match_id",
                "match_date",
                "competition",
                "season",
                "home_team",
                "away_team",
                "home_score",
                "away_score",
            ),
            "events": ("id", "match_id", "minute", "second", "type", "team", "player"),
        }

    async def _get_json(self, path: str) -> object:
        body = await self.client.get(f"{self.base_url}/{path}")
        return json.loads(body)

    def _select_pairs(self, competitions: list[dict[str, Any]]) -> list[tuple[int, int]]:
        """Decide which (competition_id, season_id) pairs to ingest.

        Explicit ``self.competitions`` wins (only those present in the open-data
        index are kept). Otherwise fall back to the bounded blind crawl.
        """

        if self.competitions:
            available = {(c["competition_id"], c["season_id"]) for c in competitions}
            selected = [p for p in self.competitions if p in available]
            missing = [p for p in self.competitions if p not in available]
            if missing:
                logger.warning("statsbomb_competitions_missing", missing=missing)
            return selected

        pairs: list[tuple[int, int]] = []
        seen: set[tuple[int, int]] = set()
        for comp in competitions:
            pair = (comp["competition_id"], comp["season_id"])
            if pair in seen:
                continue
            seen.add(pair)
            pairs.append(pair)
            if len(pairs) >= self.max_competitions:
                break
        return pairs

    async def fetch(self) -> AsyncIterator[RawRecord]:
        competitions = await self._get_json("competitions.json")
        assert isinstance(competitions, list)

        for comp_id, season_id in self._select_pairs(competitions):
            matches = await self._get_json(f"matches/{comp_id}/{season_id}.json")
            assert isinstance(matches, list)

            # max_matches_per_competition <= 0 means "all matches in the season".
            limit = self.max_matches_per_competition
            selected_matches = matches if limit <= 0 else matches[:limit]

            for match in selected_matches:
                yield RawRecord(
                    source=self.name,
                    entity="matches",
                    source_ref=str(match["match_id"]),
                    payload=match,
                )
                if not self.include_events:
                    continue
                match_id = match["match_id"]
                events = await self._get_json(f"events/{match_id}.json")
                assert isinstance(events, list)
                for event in events:
                    # Stamp match_id onto each event; the raw events file omits it.
                    event["match_id"] = match_id
                    yield RawRecord(
                        source=self.name,
                        entity="events",
                        source_ref=str(event["id"]),
                        payload=event,
                    )
