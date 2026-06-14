"""Environment-driven configuration via pydantic-settings.

Every value is sourced from the environment / `.env`; nothing (host, port,
credentials, source URLs) is hard-coded. Two profiles are supported via the
`APP_PROFILE` variable: ``local`` (console logs, debug-friendly) and ``prod``
(JSON logs). Behaviour such as log level, ingestion enable flags and source
URLs/date ranges is switched purely by environment.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Profile(StrEnum):
    LOCAL = "local"
    PROD = "prod"


class SourceSettings(BaseSettings):
    """Per-source ingestion configuration.

    Each source can be independently enabled/disabled and pointed at a base URL
    so that tests and alternate mirrors require no code change.
    """

    # env_file is set here too (not just on the top-level Settings) so that
    # SOURCE_* values in .env reach this nested model during local runs. Under
    # docker compose the env_file is injected into the real environment, which
    # also works — this makes the file-based path behave identically.
    model_config = SettingsConfigDict(
        env_prefix="SOURCE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    statsbomb_enabled: bool = True
    statsbomb_base_url: str = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"
    # Comma-separated "competition_id:season_id" pairs selecting exactly which
    # open-data competition-seasons to ingest (e.g. La Liga / Bundesliga / ...).
    # Empty -> bounded blind crawl of the first few competitions.
    statsbomb_competitions: str = ""
    # Matches to pull per competition-season; 0 means "all matches".
    statsbomb_max_matches_per_competition: int = 0
    # Per-match event files are huge; default off so a multi-league run stays
    # fast/small. Set true to also ingest events.
    statsbomb_include_events: bool = False

    openfootball_enabled: bool = True
    openfootball_base_url: str = "https://raw.githubusercontent.com/openfootball"
    # Comma-separated "repo:path" dataset list, e.g.
    # "england:2023-24/en.1.json,espana:2023-24/es.1.json". Empty -> adapter
    # default (a small sample). This is how leagues/seasons are selected.
    openfootball_datasets: str = ""

    fbref_enabled: bool = False  # HTML scraping is opt-in; defaults off to be polite.
    fbref_base_url: str = "https://fbref.com"

    understat_enabled: bool = False
    understat_base_url: str = "https://understat.com"
    # Comma-separated Understat league codes (EPL, La_liga, Serie_A,
    # Bundesliga, Ligue_1). Empty -> adapter default.
    understat_leagues: str = ""
    understat_season: str = "2023"

    # FBref hard policy cap: <= 10 requests/minute => >= 6s spacing.
    fbref_max_requests_per_minute: int = 10
    fbref_min_request_spacing_seconds: float = 6.0

    # Understat: polite throttle (not policy-mandated, but courteous).
    understat_max_requests_per_minute: int = 20


class Settings(BaseSettings):
    """Top-level application settings.

    Reads from environment variables and `.env`. The Mongo connection is fully
    described by ``MONGODB_URI`` — no host/port is ever assembled in code, so
    pointing at host Mongo vs. a compose Mongo is a config-only change.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    profile: Profile = Field(default=Profile.LOCAL, alias="APP_PROFILE")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # Fully env-driven Mongo connection. Default points at the host instance as
    # required; compose overrides it to host.docker.internal:27171.
    mongodb_uri: str = Field(
        default="mongodb://localhost:27171/?directConnection=true",
        alias="MONGODB_URI",
    )
    mongodb_database: str = Field(default="football", alias="MONGODB_DATABASE")

    # Global ingestion master switch (per-source flags live in SourceSettings).
    ingestion_enabled: bool = Field(default=True, alias="INGESTION_ENABLED")

    # Streaming batch size: how many raw records to buffer before flushing to
    # Mongo + unifying. Larger = fewer round-trips/higher throughput but more
    # memory per batch; smaller = lower memory. Bounded regardless of total size.
    ingestion_batch_size: int = Field(default=500, ge=1, le=50000, alias="INGESTION_BATCH_SIZE")

    # Optional date-range scoping for adapters that support it.
    season_start: str | None = Field(default=None, alias="SEASON_START")
    season_end: str | None = Field(default=None, alias="SEASON_END")

    sources: SourceSettings = Field(default_factory=SourceSettings)

    @property
    def is_prod(self) -> bool:
        return self.profile is Profile.PROD


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings singleton.

    Cached so the same instance is reused across the process (one config read).
    Tests can clear the cache with ``get_settings.cache_clear()``.
    """

    return Settings()
