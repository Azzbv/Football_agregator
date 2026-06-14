"""Composable ETL transform tools + the uniform step contract and registry.

Importing this package registers all built-in steps against ``registry`` (the
import of ``steps`` triggers their ``@registry.register`` decorators).
"""

from fdp_unification.transform import steps as _steps  # noqa: F401 - registers steps.
from fdp_unification.transform.contract import (
    LineageEntry,
    StepConfigBase,
    StepContext,
    StepResult,
    TransformStep,
)
from fdp_unification.transform.registry import StepRegistry, registry

__all__ = [
    "LineageEntry",
    "StepConfigBase",
    "StepContext",
    "StepRegistry",
    "StepResult",
    "TransformStep",
    "registry",
]
