"""Concrete SourcePort adapters, one module per source."""

from fdp_ingestion.adapters.fbref import FbrefAdapter
from fdp_ingestion.adapters.openfootball import OpenFootballAdapter
from fdp_ingestion.adapters.statsbomb import StatsBombAdapter
from fdp_ingestion.adapters.understat import UnderstatAdapter

__all__ = [
    "FbrefAdapter",
    "OpenFootballAdapter",
    "StatsBombAdapter",
    "UnderstatAdapter",
]
