"""The step registry: type string -> (step class, config model).

The orchestrator and API never hard-code step types — they go through the
registry. Adding a step type is a single ``register()`` call (done at import time
in ``steps.py``), after which it appears in ``GET /api/tools`` and is buildable by
the executor with no other change.
"""

from __future__ import annotations

from fdp_shared.exceptions import ValidationFailedError

from fdp_unification.transform.contract import StepConfigBase, TransformStep


class StepRegistry:
    """Maps a type string to its step class and config model."""

    def __init__(self) -> None:
        self._steps: dict[str, type[TransformStep]] = {}

    def register(self, step_cls: type[TransformStep]) -> type[TransformStep]:
        """Register a step class (usable as a decorator)."""

        self._steps[step_cls.type] = step_cls
        return step_cls

    def types(self) -> list[str]:
        return sorted(self._steps)

    def step_class(self, type_: str) -> type[TransformStep]:
        try:
            return self._steps[type_]
        except KeyError as exc:
            raise ValidationFailedError(f"unknown step type {type_!r}") from exc

    def config_model(self, type_: str) -> type[StepConfigBase]:
        return self.step_class(type_).config_model

    def build(self, type_: str, step_id: str, raw_config: dict[str, object]) -> TransformStep:
        """Validate ``raw_config`` against the step's model and construct it."""

        cls = self.step_class(type_)
        config = cls.config_model.model_validate(raw_config)
        return cls(step_id=step_id, config=config)

    def schemas(self) -> list[dict[str, object]]:
        """Return one descriptor per step type for ``GET /api/tools``."""

        out: list[dict[str, object]] = []
        for type_ in self.types():
            cls = self._steps[type_]
            out.append(
                {
                    "type": type_,
                    "title": cls.__doc__.strip().splitlines()[0] if cls.__doc__ else type_,
                    "config_schema": cls.config_model.model_json_schema(),
                }
            )
        return out


# The single process-wide registry. Steps register themselves against it.
registry = StepRegistry()
