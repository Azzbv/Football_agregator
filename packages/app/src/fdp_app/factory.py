"""Application factory — the composition root.

This is the *only* place that knows how the bounded contexts are wired together.
It constructs the single shared AsyncMongoClient, ensures indices, wires the
event bus so raw-ingest triggers unification, builds the adapter factory, and
assembles the FastAPI app with routers, middleware and error handlers.

Adapters and their PoliteClients are built per-run (not held open for the app's
lifetime) so HTTP connections are released between ingestion runs; the rate
budgets are configured from settings so the FBref <=10 req/min cap is applied by
construction.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from fdp_api.errors import register_error_handlers
from fdp_api.middleware import RequestIdMiddleware
from fdp_api.routers import (
    aggregate,
    browse,
    health,
    ingestion,
    pipelines,
    raw,
    runs,
    tools,
    unified,
)
from fdp_ingestion.adapters import (
    FbrefAdapter,
    OpenFootballAdapter,
    StatsBombAdapter,
    UnderstatAdapter,
)
from fdp_ingestion.events import EventBus
from fdp_ingestion.http import PoliteClient
from fdp_ingestion.ports import SourcePort
from fdp_ingestion.raw_repository import RawRepository
from fdp_ingestion.runner import IngestionRunner
from fdp_ingestion.status import IngestionStatusRepository
from fdp_shared.config import Settings, get_settings
from fdp_shared.logging import configure_logging, get_logger
from fdp_shared.mongo import create_client, ensure_indices
from fdp_unification.orchestration.repository import (
    LineageRepository,
    PipelineRepository,
    PipelineRunRepository,
)
from fdp_unification.service import UnificationService

logger = get_logger(__name__)


def _build_adapters(settings: Settings) -> list[SourcePort]:
    """Construct the enabled source adapters with per-source polite clients.

    Each adapter gets its own PoliteClient so rate budgets don't interfere.
    FBref's client is constructed with the policy cap (<=10 rpm, >=6s spacing).
    """

    s = settings.sources
    adapters: list[SourcePort] = []

    if s.statsbomb_enabled:
        sb_competitions = [
            (int(item.split(":", 1)[0]), int(item.split(":", 1)[1]))
            for item in s.statsbomb_competitions.split(",")
            if ":" in item
        ]
        adapters.append(
            StatsBombAdapter(
                base_url=s.statsbomb_base_url,
                client=PoliteClient(requests_per_minute=60),
                competitions=sb_competitions,
                max_matches_per_competition=s.statsbomb_max_matches_per_competition,
                include_events=s.statsbomb_include_events,
            )
        )
    if s.openfootball_enabled:
        of_kwargs: dict[str, object] = {
            "base_url": s.openfootball_base_url,
            "client": PoliteClient(requests_per_minute=60),
        }
        datasets = [
            (item.split(":", 1)[0].strip(), item.split(":", 1)[1].strip())
            for item in s.openfootball_datasets.split(",")
            if ":" in item
        ]
        if datasets:
            of_kwargs["datasets"] = datasets
        adapters.append(OpenFootballAdapter(**of_kwargs))  # type: ignore[arg-type]
    if s.fbref_enabled:
        adapters.append(
            FbrefAdapter(
                base_url=s.fbref_base_url,
                client=PoliteClient(
                    requests_per_minute=s.fbref_max_requests_per_minute,
                    min_spacing_seconds=s.fbref_min_request_spacing_seconds,
                ),
            )
        )
    if s.understat_enabled:
        us_kwargs: dict[str, object] = {
            "base_url": s.understat_base_url,
            "client": PoliteClient(requests_per_minute=s.understat_max_requests_per_minute),
            "season": s.understat_season,
        }
        leagues = tuple(x.strip() for x in s.understat_leagues.split(",") if x.strip())
        if leagues:
            us_kwargs["leagues"] = leagues
        adapters.append(UnderstatAdapter(**us_kwargs))  # type: ignore[arg-type]
    return adapters


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build and wire the FastAPI application."""

    settings = settings or get_settings()
    configure_logging(settings.profile, settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        client = create_client(settings.mongodb_uri)
        db = client[settings.mongodb_database]
        await ensure_indices(db)
        await PipelineRepository(db).ensure_indices()
        await PipelineRunRepository(db).ensure_indices()
        await LineageRepository(db).ensure_indices()

        bus = EventBus()
        unifier = UnificationService(db)
        bus.subscribe(unifier.handle_raw_ingested)

        runner = IngestionRunner(
            raw_repo=RawRepository(db),
            status_repo=IngestionStatusRepository(db),
            event_bus=bus,
            batch_size=settings.ingestion_batch_size,
        )

        app.state.settings = settings
        app.state.mongo_client = client
        app.state.db = db
        app.state.event_bus = bus
        app.state.unifier = unifier
        app.state.ingestion_runner = runner
        app.state.build_adapters = lambda: _build_adapters(settings)

        logger.info("app_started", profile=settings.profile.value)
        try:
            yield
        finally:
            await client.close()
            logger.info("app_stopped")

    app = FastAPI(
        title="Football Data Platform",
        version="0.1.0",
        summary="Ingest, unify and browse open football data.",
        lifespan=lifespan,
    )

    app.add_middleware(RequestIdMiddleware)
    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(raw.router)
    app.include_router(unified.router)
    app.include_router(ingestion.router)
    app.include_router(tools.router)
    app.include_router(pipelines.router)
    app.include_router(runs.router)
    app.include_router(browse.router)
    app.include_router(aggregate.router)

    try:
        from fdp_ui import mount_ui

        mount_ui(app)
    except Exception as exc:
        logger.warning("ui_not_mounted", error=str(exc))

    return app
