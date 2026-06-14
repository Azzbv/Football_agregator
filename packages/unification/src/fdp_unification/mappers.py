"""Anti-corruption layer: map source-shaped raw records to unified domain models.

Each source has fundamentally different field names and shapes; the ACL absorbs
that variation so the rest of the platform only ever sees the unified
:mod:`fdp_shared.domain` models. A mapper takes a :class:`RawRecord` and returns
zero or more ``(collection, unified_model)`` pairs. Fields the unified contract
does not need are discarded here — this is the boundary that keeps source
vocabulary out of the core domain.

Mappers are pure and total: a record they don't understand yields ``[]`` rather
than raising, so one odd row never aborts a batch. Validation failures (a record
that should map but is malformed) raise :class:`ValidationFailedError`.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any, Protocol

from fdp_ingestion.ports import RawRecord
from fdp_shared.domain import (
    Event,
    Match,
    PlayerStats,
    SourceName,
    Team,
    TeamStats,
)
from fdp_shared.exceptions import ValidationFailedError
from fdp_shared.logging import get_logger
from fdp_unification.keys import unified_id

logger = get_logger(__name__)

# (collection_name, unified_model_instance)
Mapped = tuple[str, Any]

# Coercion errors we treat as "not convertible -> None".
_COERCE_ERRORS = (TypeError, ValueError)


def _to_int(value: Any) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except _COERCE_ERRORS:
        return None


def _to_float(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except _COERCE_ERRORS:
        return None


class Mapper(Protocol):
    """Maps raw records for a single source into unified models."""

    source: SourceName

    def map(self, record: RawRecord) -> Iterable[Mapped]: ...


class StatsBombMapper:
    source = SourceName.STATSBOMB

    def map(self, record: RawRecord) -> Iterable[Mapped]:
        p = record.payload
        if record.entity == "matches":
            mid = unified_id(self.source, record.source_ref)
            home = p["home_team"]
            away = p["away_team"]
            yield (
                "matches",
                Match(
                    source=self.source,
                    source_ref=record.source_ref,
                    ingested_at=datetime.now(UTC),
                    match_id=mid,
                    competition=(p.get("competition") or {}).get("competition_name"),
                    season_id=(p.get("season") or {}).get("season_name"),
                    match_date=_parse_date(p.get("match_date")),
                    home_team=Team(team_id=str(home["home_team_id"]), name=home["home_team_name"]),
                    away_team=Team(team_id=str(away["away_team_id"]), name=away["away_team_name"]),
                    home_score=_to_int(p.get("home_score")),
                    away_score=_to_int(p.get("away_score")),
                ),
            )
        elif record.entity == "events":
            # StatsBomb event shape: id, minute, second, type.name, team.id,
            # player.id, location [x, y]. match_id is stamped by the adapter.
            # The unified Event.match_id references the unified match id so it
            # joins cleanly against the matches collection.
            raw_match_id = p.get("match_id")
            location = p.get("location") or [None, None]
            team = p.get("team") or {}
            player = p.get("player") or {}
            yield (
                "events",
                Event(
                    source=self.source,
                    source_ref=record.source_ref,
                    ingested_at=datetime.now(UTC),
                    event_id=unified_id(self.source, record.source_ref),
                    match_id=unified_id(self.source, str(raw_match_id)),
                    minute=_to_int(p.get("minute")),
                    second=_to_int(p.get("second")),
                    team_id=str(team["id"]) if team.get("id") is not None else None,
                    player_id=str(player["id"]) if player.get("id") is not None else None,
                    event_type=(p.get("type") or {}).get("name", "Unknown"),
                    x=_to_float(location[0]) if len(location) > 0 else None,
                    y=_to_float(location[1]) if len(location) > 1 else None,
                ),
            )


class OpenFootballMapper:
    source = SourceName.OPENFOOTBALL

    def map(self, record: RawRecord) -> Iterable[Mapped]:
        p = record.payload
        if record.entity == "matches":
            mid = unified_id(self.source, record.source_ref)
            score = (p.get("score") or {}).get("ft") or [None, None]
            yield (
                "matches",
                Match(
                    source=self.source,
                    source_ref=record.source_ref,
                    ingested_at=datetime.now(UTC),
                    match_id=mid,
                    competition=p.get("league"),
                    season_id=p.get("season"),
                    match_date=_parse_date(p.get("date")),
                    home_team=Team(team_id=_slug(p["team1"]), name=p["team1"]),
                    away_team=Team(team_id=_slug(p["team2"]), name=p["team2"]),
                    home_score=_to_int(score[0]),
                    away_score=_to_int(score[1]),
                ),
            )


class UnderstatMapper:
    source = SourceName.UNDERSTAT

    def map(self, record: RawRecord) -> Iterable[Mapped]:
        p = record.payload
        if record.entity == "matches":
            mid = unified_id(self.source, record.source_ref)
            home = p.get("h") or {}
            away = p.get("a") or {}
            goals = p.get("goals") or {}
            xg = p.get("xG") or {}
            yield (
                "matches",
                Match(
                    source=self.source,
                    source_ref=record.source_ref,
                    ingested_at=datetime.now(UTC),
                    match_id=mid,
                    competition=p.get("league"),
                    season_id=p.get("season"),
                    match_date=_parse_date(p.get("datetime")),
                    home_team=Team(team_id=str(home.get("id")), name=home.get("title", "")),
                    away_team=Team(team_id=str(away.get("id")), name=away.get("title", "")),
                    home_score=_to_int(goals.get("h")),
                    away_score=_to_int(goals.get("a")),
                ),
            )
            # Understat also gives per-side xG -> team_stats.
            for side, team in (("h", home), ("a", away)):
                yield (
                    "team_stats",
                    TeamStats(
                        source=self.source,
                        source_ref=f"{record.source_ref}:{side}",
                        ingested_at=datetime.now(UTC),
                        match_id=mid,
                        season_id=p.get("season"),
                        team_id=str(team.get("id")),
                        goals=_to_int(goals.get(side)),
                        xg=_to_float(xg.get(side)),
                    ),
                )


class FbrefMapper:
    source = SourceName.FBREF

    def map(self, record: RawRecord) -> Iterable[Mapped]:
        p = record.payload
        if record.entity == "player_stats":
            pid = unified_id(self.source, record.source_ref)
            yield (
                "player_stats",
                PlayerStats(
                    source=self.source,
                    source_ref=record.source_ref,
                    ingested_at=datetime.now(UTC),
                    player_id=pid,
                    team_id=_slug(p.get("team", "")) or None,
                    goals=_to_int(p.get("goals")),
                    assists=_to_int(p.get("assists")),
                    shots=_to_int(p.get("shots")),
                    minutes=_to_int(p.get("minutes")),
                ),
            )


def _slug(value: str) -> str:
    return value.strip().lower().replace(" ", "-")


def _parse_date(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).replace("Z", "+00:00")
    for parse in (datetime.fromisoformat,):
        try:
            return parse(text)
        except ValueError:
            continue
    # Date-only fallback.
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError as exc:
        raise ValidationFailedError(f"unparseable date {value!r}") from exc


_REGISTRY: dict[SourceName, Mapper] = {
    SourceName.STATSBOMB: StatsBombMapper(),
    SourceName.OPENFOOTBALL: OpenFootballMapper(),
    SourceName.UNDERSTAT: UnderstatMapper(),
    SourceName.FBREF: FbrefMapper(),
}


def get_mapper(source: SourceName) -> Mapper:
    """Return the ACL mapper registered for ``source``."""

    return _REGISTRY[source]
