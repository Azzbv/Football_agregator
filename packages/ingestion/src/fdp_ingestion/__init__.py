"""Ingestion bounded context: ports, adapters, runner, status tracking.

Public surface consumed by the composition root (``app``).
"""

from fdp_ingestion.adapters import (
    FbrefAdapter,
    OpenFootballAdapter,
    StatsBombAdapter,
    UnderstatAdapter,
)
from fdp_ingestion.events import EventBus, RawIngested
from fdp_ingestion.http import PoliteClient
from fdp_ingestion.ports import RawRecord, SourcePort
from fdp_ingestion.raw_repository import RawRepository, raw_collection_name
from fdp_ingestion.runner import IngestionRunner
from fdp_ingestion.status import IngestionStatusRepository, RunStatus

__all__ = [
    "EventBus",
    "FbrefAdapter",
    "IngestionRunner",
    "IngestionStatusRepository",
    "OpenFootballAdapter",
    "PoliteClient",
    "RawIngested",
    "RawRecord",
    "RawRepository",
    "RunStatus",
    "SourcePort",
    "StatsBombAdapter",
    "UnderstatAdapter",
    "raw_collection_name",
]
