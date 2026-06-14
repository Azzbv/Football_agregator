"""The uniform transform-step contract.

Every step — no matter what it does — implements the same tiny interface so the
orchestrator can compose them generically:

* constructed from a typed Pydantic ``config`` model (validation is free, and the
  model's JSON schema drives the UI's dynamic forms);
* ``apply(ctx) -> StepResult`` reads/writes ``ctx.record`` (a mutable working
  record) and returns *what changed* as explicit, structured lineage — never as
  a side effect. A step that mutates data without emitting lineage is incorrect.

Adding a new step type is: subclass ``TransformStep``, define its config model,
register the pair. No orchestrator or UI change is needed.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar

from pydantic import BaseModel, Field


class LineageEntry(BaseModel):
    """One structured record of a change a step made (or chose not to make)."""

    step_id: str
    step_type: str
    source_paths: list[str] = Field(default_factory=list)
    target_path: str | None = None
    before_value: Any = None
    after_value: Any = None
    note: str | None = None


class StepContext(BaseModel):
    """Mutable per-record context threaded through the pipeline."""

    model_config = {"arbitrary_types_allowed": True}

    step_id: str
    record: dict[str, Any]
    # Set by a ``filter`` step to signal the record should be discarded.
    dropped: bool = False
    drop_reason: str | None = None


class StepResult(BaseModel):
    """What a step returns: the lineage it produced, plus drop signalling."""

    lineage: list[LineageEntry] = Field(default_factory=list)
    dropped: bool = False
    drop_reason: str | None = None


# Alias for the config-model type, captured before any class shadows ``type``.
_ConfigModelType = type["StepConfigBase"]


class StepConfigBase(BaseModel):
    """Base for every step's typed config model.

    ``model_config`` forbids extras so a misconfigured step fails validation
    (surfaced to the UI) rather than silently ignoring fields.
    """

    model_config = {"extra": "forbid"}


class TransformStep(ABC):
    """Abstract base every concrete step implements.

    ``type`` is the registry key and the ``StepConfig.type`` discriminator.
    ``config_model`` is the Pydantic model whose JSON schema drives the UI form.
    """

    # NB: a ClassVar named ``type`` shadows the ``type`` builtin inside the class
    # body, so we alias it for annotations that need the builtin.
    type: ClassVar[str]
    config_model: ClassVar[_ConfigModelType]

    def __init__(self, step_id: str, config: StepConfigBase) -> None:
        self.step_id = step_id
        self.config = config

    @abstractmethod
    def apply(self, ctx: StepContext) -> StepResult:
        """Mutate ``ctx.record`` and return structured lineage."""

    def _entry(self, **kwargs: Any) -> LineageEntry:
        """Helper to stamp step identity onto a LineageEntry."""

        return LineageEntry(step_id=self.step_id, step_type=self.type, **kwargs)
