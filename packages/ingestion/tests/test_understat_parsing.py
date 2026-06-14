"""Understat decoder test: decodes the hex-escaped <script> JSON payload.

No DOM-table scraping — we assert the script-var decode recovers the structured
fixtures, exactly as the adapter does against the live page.
"""

from __future__ import annotations

from pathlib import Path

from fdp_ingestion.adapters.understat import decode_script_var

FIXTURE = Path(__file__).parent / "fixtures" / "understat_sample.html"


def test_decode_dates_data() -> None:
    html = FIXTURE.read_text(encoding="utf-8")
    fixtures = decode_script_var(html, "datesData")
    assert isinstance(fixtures, list)
    assert len(fixtures) == 2
    first = fixtures[0]
    assert first["id"] == "1001"
    assert first["h"]["title"] == "Arsenal"
    assert first["goals"]["h"] == "2"
    assert first["xG"]["h"] == "1.85"
