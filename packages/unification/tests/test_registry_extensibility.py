"""Proves the extensibility acceptance criterion.

Adding a new step type requires only a new step class + config model + registry
entry — no orchestrator or UI change. Here we register a brand-new step against a
fresh registry, build it through the generic registry path, and confirm it runs
and exposes its JSON schema (which is exactly what drives the UI form).
"""

from __future__ import annotations

from typing import ClassVar

from fdp_unification.transform.contract import (
    StepConfigBase,
    StepContext,
    StepResult,
    TransformStep,
)
from fdp_unification.transform.paths import get_path, set_path
from fdp_unification.transform.registry import StepRegistry


class UppercaseConfig(StepConfigBase):
    target_path: str


class UppercaseStep(TransformStep):
    """Uppercase a string field."""

    type: ClassVar[str] = "uppercase"
    config_model: ClassVar[type[StepConfigBase]] = UppercaseConfig

    def apply(self, ctx: StepContext) -> StepResult:
        before = get_path(ctx.record, self.config.target_path)  # type: ignore[attr-defined]
        after = before.upper() if isinstance(before, str) else before
        set_path(ctx.record, self.config.target_path, after)  # type: ignore[attr-defined]
        return StepResult(
            lineage=[self._entry(target_path=self.config.target_path, before_value=before, after_value=after)]  # type: ignore[attr-defined]
        )


def test_new_step_type_works_via_registry_only() -> None:
    reg = StepRegistry()
    reg.register(UppercaseStep)

    # Discoverable for the UI (GET /api/tools) with its JSON schema.
    schemas = reg.schemas()
    assert any(s["type"] == "uppercase" for s in schemas)
    uppercase_schema = next(s for s in schemas if s["type"] == "uppercase")
    assert "target_path" in uppercase_schema["config_schema"]["properties"]

    # Buildable + runnable through the generic registry path.
    step = reg.build("uppercase", "s1", {"target_path": "name"})
    ctx = StepContext(step_id="s1", record={"name": "arsenal"})
    result = step.apply(ctx)
    assert ctx.record["name"] == "ARSENAL"
    assert result.lineage[0].after_value == "ARSENAL"
