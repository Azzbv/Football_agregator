"""Service-layer unit tests for the ACL mappers (no DB, no network)."""

from __future__ import annotations

import json
from pathlib import Path

from fdp_ingestion.ports import RawRecord
from fdp_shared.domain import Event, Match, SourceName, TeamStats
from fdp_unification.keys import unified_id
from fdp_unification.mappers import get_mapper

SB_MATCH = Path(__file__).parents[2] / "ingestion" / "tests" / "fixtures" / "statsbomb_match.json"


def test_statsbomb_match_maps_to_unified() -> None:
    payload = json.loads(SB_MATCH.read_text(encoding="utf-8"))
    record = RawRecord(
        source=SourceName.STATSBOMB,
        entity="matches",
        source_ref=str(payload["match_id"]),
        payload=payload,
    )
    mapped = list(get_mapper(SourceName.STATSBOMB).map(record))
    assert len(mapped) == 1
    collection, model = mapped[0]
    assert collection == "matches"
    assert isinstance(model, Match)
    assert model.match_id == unified_id(SourceName.STATSBOMB, "3895302")
    assert model.home_team.name == "Arsenal"
    assert model.home_score == 2
    assert model.competition == "Premier League"


def test_statsbomb_event_maps_to_unified() -> None:
    # Real StatsBomb event shape (adapter stamps match_id onto each event).
    payload = {
        "id": "6c546c19-5f61-4236-a1ad-0b6f5cded692",
        "match_id": 3895292,
        "minute": 0,
        "second": 1,
        "type": {"id": 30, "name": "Pass"},
        "team": {"id": 190, "name": "Union Berlin"},
        "player": {"id": 24243, "name": "Brenden Aaronson"},
        "location": [61.0, 40.1],
    }
    record = RawRecord(
        source=SourceName.STATSBOMB,
        entity="events",
        source_ref=payload["id"],
        payload=payload,
    )
    mapped = list(get_mapper(SourceName.STATSBOMB).map(record))
    assert len(mapped) == 1
    collection, model = mapped[0]
    assert collection == "events"
    assert isinstance(model, Event)
    assert model.event_id == unified_id(SourceName.STATSBOMB, payload["id"])
    # Event links to the unified match id, joinable against `matches`.
    assert model.match_id == unified_id(SourceName.STATSBOMB, "3895292")
    assert model.event_type == "Pass"
    assert model.team_id == "190"
    assert model.player_id == "24243"
    assert model.minute == 0 and model.second == 1
    assert model.x == 61.0 and model.y == 40.1


def test_openfootball_synthesises_id_and_score() -> None:
    record = RawRecord(
        source=SourceName.OPENFOOTBALL,
        entity="matches",
        source_ref="2023-08-12:arsenal:chelsea",
        payload={
            "date": "2023-08-12",
            "team1": "Arsenal",
            "team2": "Chelsea",
            "score": {"ft": [2, 1]},
            "league": "Premier League",
            "season": "2023-24",
        },
    )
    ((collection, model),) = list(get_mapper(SourceName.OPENFOOTBALL).map(record))
    assert collection == "matches"
    assert model.home_score == 2 and model.away_score == 1
    assert model.home_team.team_id == "arsenal"


def test_understat_emits_match_and_team_stats_with_xg() -> None:
    record = RawRecord(
        source=SourceName.UNDERSTAT,
        entity="matches",
        source_ref="1001",
        payload={
            "id": "1001",
            "h": {"id": "81", "title": "Arsenal"},
            "a": {"id": "82", "title": "Chelsea"},
            "goals": {"h": "2", "a": "1"},
            "xG": {"h": "1.85", "a": "0.94"},
            "datetime": "2023-08-12 17:30:00",
            "league": "EPL",
            "season": "2023",
        },
    )
    mapped = list(get_mapper(SourceName.UNDERSTAT).map(record))
    collections = [c for c, _ in mapped]
    assert collections.count("matches") == 1
    assert collections.count("team_stats") == 2
    team_stats = [m for c, m in mapped if c == "team_stats"]
    assert isinstance(team_stats[0], TeamStats)
    assert team_stats[0].xg == 1.85
