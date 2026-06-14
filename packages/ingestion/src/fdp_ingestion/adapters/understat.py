"""Understat adapter — JSON embedded inside <script> tags.

Understat does NOT render its match/shot/xG data into DOM tables. Instead each
page ships the data as a JS string literal inside a ``<script>`` block, e.g.::

    var datesData = JSON.parse('\\x5B\\x7B\\x22id...');

The payload is a JSON string that has been *hex-escaped* (``\\xNN``). To decode
it we:

1. locate the assignment for the variable we want,
2. extract the single-quoted string literal,
3. undo the ``\\xNN`` escaping to recover raw JSON text,
4. ``json.loads`` it.

We decode the script payload directly — we never scrape DOM tables (there are
none). Throttled politely via the injected :class:`PoliteClient`.
"""

from __future__ import annotations

import codecs
import json
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass

from fdp_shared.domain import SourceName
from fdp_shared.exceptions import IngestionError
from fdp_shared.logging import get_logger

from fdp_ingestion.http import PoliteClient
from fdp_ingestion.ports import RawRecord

logger = get_logger(__name__)


def decode_script_var(html: str, var_name: str) -> object:
    """Extract and JSON-decode an Understat ``var_name = JSON.parse('...')`` blob.

    Raises :class:`IngestionError` if the variable is not present.
    """

    # Match: <var> = JSON.parse('<single-quoted, hex-escaped json>')
    pattern = re.compile(
        rf"{re.escape(var_name)}\s*=\s*JSON\.parse\('(?P<payload>.*?)'\)",
        re.DOTALL,
    )
    match = pattern.search(html)
    if match is None:
        raise IngestionError("understat", f"variable {var_name!r} not found in page")

    escaped = match.group("payload")
    # The payload uses \xNN hex escapes; unicode_escape reverses them to get the
    # original JSON source text, which we then parse.
    raw_json = codecs.decode(escaped, "unicode_escape")
    return json.loads(raw_json)


@dataclass
class UnderstatAdapter:
    """Adapter that decodes Understat's embedded JSON script payloads."""

    base_url: str
    client: PoliteClient
    leagues: tuple[str, ...] = ("EPL",)
    season: str = "2023"

    @property
    def name(self) -> SourceName:
        return SourceName.UNDERSTAT

    @property
    def extracted_fields(self) -> dict[str, tuple[str, ...]]:
        return {
            "matches": ("id", "h", "a", "goals", "xG", "datetime"),
        }

    async def fetch(self) -> AsyncIterator[RawRecord]:
        for league in self.leagues:
            url = f"{self.base_url}/league/{league}/{self.season}"
            body = await self.client.get(url)
            html = body.decode("utf-8", errors="replace")
            # `datesData` holds the fixture list with embedded xG/goals.
            fixtures = decode_script_var(html, "datesData")
            assert isinstance(fixtures, list)
            for fixture in fixtures:
                yield RawRecord(
                    source=self.name,
                    entity="matches",
                    source_ref=str(fixture["id"]),
                    payload={**fixture, "league": league, "season": self.season},
                )
