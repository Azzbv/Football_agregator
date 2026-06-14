"""FBref (Sports Reference) adapter — real HTML extraction.

Two FBref-specific quirks are handled here:

1. **Rate policy.** Sports Reference's bot policy caps clients at <= 10
   requests/minute. The :class:`PoliteClient` injected here is configured with
   ``requests_per_minute=10`` *and* ``min_spacing_seconds=6.0`` so every request
   is at least 6 seconds apart — the cap is enforced by construction, not by
   convention. (See the rate-limiter test which asserts the spacing.)

2. **Commented-out tables.** Many FBref stat tables are wrapped in HTML comments
   (``<!-- <div ...><table>...</table></div> -->``) to defer rendering. A naive
   DOM parser never sees them. We therefore extract the comment bodies, strip the
   comment delimiters, and re-parse that fragment so the hidden tables become
   first-class nodes.

We only extract the fields we declare in ``extracted_fields``; the rest of the
page is discarded.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from dataclasses import dataclass

from selectolax.parser import HTMLParser

from fdp_shared.domain import SourceName
from fdp_shared.logging import get_logger

from fdp_ingestion.http import PoliteClient
from fdp_ingestion.ports import RawRecord

logger = get_logger(__name__)

# Matches the bodies of HTML comments so we can re-parse hidden tables.
_COMMENT_RE = re.compile(r"<!--(.*?)-->", re.DOTALL)


def uncomment_tables(html: str) -> str:
    """Return ``html`` with comment-wrapped table markup promoted to live nodes.

    FBref hides many ``<table>`` blocks inside HTML comments. We splice the
    comment bodies that contain a ``<table`` back into the document so a single
    parse sees both the originally-live and the originally-commented tables.
    """

    def _replace(match: re.Match[str]) -> str:
        body = match.group(1)
        return body if "<table" in body else match.group(0)

    return _COMMENT_RE.sub(_replace, html)


@dataclass
class FbrefAdapter:
    """Rate-limited HTML adapter for FBref stat tables."""

    base_url: str
    client: PoliteClient
    # Page paths to scrape. Each is a stats table page; defaults to a single
    # well-known page to keep the polite request budget small.
    paths: tuple[str, ...] = ("/en/comps/9/Premier-League-Stats",)

    @property
    def name(self) -> SourceName:
        return SourceName.FBREF

    @property
    def extracted_fields(self) -> dict[str, tuple[str, ...]]:
        return {
            "player_stats": ("player", "team", "goals", "assists", "shots", "minutes"),
            "team_stats": ("team", "goals", "possession", "shots"),
        }

    def _parse_player_rows(self, html: str) -> list[dict[str, str]]:
        """Parse the (possibly comment-hidden) standard-stats table.

        FBref rows carry ``data-stat`` attributes; we read only the columns we
        declared, keyed by their canonical names.
        """

        tree = HTMLParser(uncomment_tables(html))
        table = tree.css_first("table#stats_standard, table[id*='stats_standard']")
        if table is None:
            return []

        wanted = {
            "player": "player",
            "team": "team",
            "goals": "goals",
            "assists": "assists",
            "shots": "shots_total",
            "minutes": "minutes",
        }
        rows: list[dict[str, str]] = []
        for tr in table.css("tbody tr"):
            if "thead" in (tr.attributes.get("class") or ""):
                continue
            record: dict[str, str] = {}
            for out_key, stat in wanted.items():
                cell = tr.css_first(f"[data-stat='{stat}']")
                if cell is not None:
                    record[out_key] = cell.text(strip=True)
            if record.get("player"):
                rows.append(record)
        return rows

    async def fetch(self) -> AsyncIterator[RawRecord]:
        for path in self.paths:
            url = f"{self.base_url}{path}"
            body = await self.client.get(url)
            html = body.decode("utf-8", errors="replace")
            for idx, row in enumerate(self._parse_player_rows(html)):
                ref = f"{path}:{row.get('player', '')}:{idx}"
                yield RawRecord(
                    source=self.name,
                    entity="player_stats",
                    source_ref=ref,
                    payload={**row, "page": path},
                )
