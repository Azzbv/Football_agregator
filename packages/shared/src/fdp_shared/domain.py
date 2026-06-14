"""Unified domain DTOs (Pydantic v2).

These are the *unified* representations persisted into the normalized
collections (``matches``, ``events``, ``players``, ``team_stats``,
``player_stats``). They are deliberately source-agnostic: the anti-corruption
layer in the ``unification`` package maps raw, source-shaped documents onto
these models, discarding fields no source-common contract needs.

Every model carries ``source`` and ``source_ref`` provenance plus the composite
natural key used for idempotent upserts (see ``unification`` for derivation).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class SourceName(StrEnum):
    STATSBOMB = "statsbomb"
    OPENFOOTBALL = "openfootball"
    FBREF = "fbref"
    UNDERSTAT = "understat"


class _UnifiedBase(BaseModel):
    """Common base for all unified documents."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    source: SourceName
    source_ref: str = Field(description="Native identifier in the originating source.")
    ingested_at: datetime | None = Field(
        default=None, description="UTC timestamp set when the record was unified."
    )


class Team(BaseModel):
    model_config = ConfigDict(extra="forbid")

    team_id: str
    name: str


class Match(_UnifiedBase):
    """A single fixture."""

    match_id: str = Field(description="Unified deterministic id: '{source}:{source_ref}'.")
    league_id: str | None = None
    season_id: str | None = None
    competition: str | None = None
    match_date: datetime | None = None
    home_team: Team
    away_team: Team
    home_score: int | None = None
    away_score: int | None = None


class Event(_UnifiedBase):
    """A single in-match event (pass, shot, etc.)."""

    event_id: str
    match_id: str
    minute: int | None = None
    second: int | None = None
    team_id: str | None = None
    player_id: str | None = None
    event_type: str
    x: float | None = None
    y: float | None = None


class Player(_UnifiedBase):
    player_id: str
    name: str
    country: str | None = None
    position: str | None = None


class TeamStats(_UnifiedBase):
    """Aggregated team stats for a match (or season window)."""

    match_id: str | None = None
    league_id: str | None = None
    season_id: str | None = None
    team_id: str
    goals: int | None = None
    xg: float | None = None
    shots: int | None = None
    possession: float | None = None


class PlayerStats(_UnifiedBase):
    """Aggregated player stats for a match (or season window)."""

    match_id: str | None = None
    league_id: str | None = None
    season_id: str | None = None
    player_id: str
    team_id: str | None = None
    minutes: int | None = None
    goals: int | None = None
    assists: int | None = None
    xg: float | None = None
    shots: int | None = None


class MatchAggregate(BaseModel):
    """A denormalized match: the fixture with all related entities embedded.

    Materialized into the ``match_aggregates`` collection by joining the
    normalized collections on ``match_id`` (players are resolved from the ids
    referenced by the match's events and player_stats). This is the "everything
    about one match in a single object" view the JSON preview renders.
    """

    model_config = ConfigDict(extra="forbid")

    match_id: str
    match: Match
    team_stats: list[TeamStats] = Field(default_factory=list)
    player_stats: list[PlayerStats] = Field(default_factory=list)
    events: list[Event] = Field(default_factory=list)
    players: list[Player] = Field(default_factory=list)
    total_events: int = Field(default=0, description="Count of embedded events.")
    built_at: datetime | None = Field(
        default=None, description="UTC timestamp this aggregate was last materialized."
    )
