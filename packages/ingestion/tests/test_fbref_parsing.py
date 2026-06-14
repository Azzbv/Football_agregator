"""FBref adapter test: parses a local fixture, no live network.

Asserts the comment-unwrapping works — the stats table in the fixture is wrapped
in an HTML comment, so a naive parse would find zero rows.
"""

from __future__ import annotations

from pathlib import Path

from fdp_ingestion.adapters.fbref import FbrefAdapter, uncomment_tables
from fdp_ingestion.http import PoliteClient

FIXTURE = Path(__file__).parent / "fixtures" / "fbref_sample.html"


def test_uncomment_promotes_hidden_table() -> None:
    html = FIXTURE.read_text(encoding="utf-8")
    # The table is inside a comment in the raw HTML...
    assert "<!--" in html
    promoted = uncomment_tables(html)
    # ...and after un-commenting the <table ...> is live markup.
    assert "<table id=\"stats_standard\">" in promoted
    assert promoted.count("<!--") == 0


def test_parse_player_rows_from_commented_table() -> None:
    html = FIXTURE.read_text(encoding="utf-8")
    adapter = FbrefAdapter(base_url="https://fbref.test", client=PoliteClient(requests_per_minute=10))
    rows = adapter._parse_player_rows(html)
    assert len(rows) == 2
    haaland = rows[0]
    assert haaland["player"] == "Erling Haaland"
    assert haaland["goals"] == "27"
    assert haaland["minutes"] == "2557"
