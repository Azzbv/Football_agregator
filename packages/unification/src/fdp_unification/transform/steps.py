"""The built-in transform steps.

Each step is single-purpose, declaratively configured via a typed Pydantic
config model, and emits structured lineage for everything it changes. They all
register themselves against the shared ``registry`` at import time, so importing
this module is what populates ``GET /api/tools`` and the executor's vocabulary.

To add a new step type: subclass ``TransformStep``, give it a ``type`` and a
``config_model``, decorate with ``@registry.register``. Nothing else changes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar, Literal

from jsonpath_ng.ext import parse as jsonpath_parse  # ext = supports filters
from pydantic import Field

from fdp_unification.transform.contract import (
    StepConfigBase,
    StepContext,
    StepResult,
    TransformStep,
)
from fdp_unification.transform.paths import (
    delete_path,
    get_path,
    has_path,
    set_path,
)
from fdp_unification.transform.registry import registry

# --------------------------------------------------------------------------- #
# extract
# --------------------------------------------------------------------------- #


class ExtractConfig(StepConfigBase):
    source_path: str = Field(description="Dot-path or JSONPath into the source record.")
    target_path: str = Field(description="Where to write the extracted value.")
    jsonpath: bool = Field(default=False, description="Treat source_path as JSONPath.")


@registry.register
class ExtractStep(TransformStep):
    """Extract a value at a source path into a target field."""

    type: ClassVar[str] = "extract"
    config_model: ClassVar[type[StepConfigBase]] = ExtractConfig

    def apply(self, ctx: StepContext) -> StepResult:
        cfg: ExtractConfig = self.config  # type: ignore[assignment]
        if cfg.jsonpath:
            matches = jsonpath_parse(cfg.source_path).find(ctx.record)
            value = matches[0].value if matches else None
        else:
            value = get_path(ctx.record, cfg.source_path)
        before = get_path(ctx.record, cfg.target_path)
        set_path(ctx.record, cfg.target_path, value)
        return StepResult(
            lineage=[
                self._entry(
                    source_paths=[cfg.source_path],
                    target_path=cfg.target_path,
                    before_value=before,
                    after_value=value,
                    note="jsonpath" if cfg.jsonpath else "dot-path",
                )
            ]
        )


# --------------------------------------------------------------------------- #
# rename
# --------------------------------------------------------------------------- #


class RenameConfig(StepConfigBase):
    source_path: str
    target_path: str


@registry.register
class RenameStep(TransformStep):
    """Move a field from one key to another."""

    type: ClassVar[str] = "rename"
    config_model: ClassVar[type[StepConfigBase]] = RenameConfig

    def apply(self, ctx: StepContext) -> StepResult:
        cfg: RenameConfig = self.config  # type: ignore[assignment]
        before_target = get_path(ctx.record, cfg.target_path)
        value = delete_path(ctx.record, cfg.source_path)
        set_path(ctx.record, cfg.target_path, value)
        return StepResult(
            lineage=[
                self._entry(
                    source_paths=[cfg.source_path],
                    target_path=cfg.target_path,
                    before_value=before_target,
                    after_value=value,
                    note=f"renamed {cfg.source_path} -> {cfg.target_path}",
                )
            ]
        )


# --------------------------------------------------------------------------- #
# duplicate (copy)
# --------------------------------------------------------------------------- #


class DuplicateConfig(StepConfigBase):
    source_path: str
    target_path: str


@registry.register
class DuplicateStep(TransformStep):
    """Copy a field's value to another field, keeping the original."""

    type: ClassVar[str] = "duplicate"
    config_model: ClassVar[type[StepConfigBase]] = DuplicateConfig

    def apply(self, ctx: StepContext) -> StepResult:
        cfg: DuplicateConfig = self.config  # type: ignore[assignment]
        value = get_path(ctx.record, cfg.source_path)
        before = get_path(ctx.record, cfg.target_path)
        set_path(ctx.record, cfg.target_path, value)
        return StepResult(
            lineage=[
                self._entry(
                    source_paths=[cfg.source_path],
                    target_path=cfg.target_path,
                    before_value=before,
                    after_value=value,
                    note="copied (original kept)",
                )
            ]
        )


# --------------------------------------------------------------------------- #
# constant
# --------------------------------------------------------------------------- #


class ConstantConfig(StepConfigBase):
    target_path: str
    value: Any = Field(description="Literal value to set.")


@registry.register
class ConstantStep(TransformStep):
    """Set a target field to a fixed literal value."""

    type: ClassVar[str] = "constant"
    config_model: ClassVar[type[StepConfigBase]] = ConstantConfig

    def apply(self, ctx: StepContext) -> StepResult:
        cfg: ConstantConfig = self.config  # type: ignore[assignment]
        before = get_path(ctx.record, cfg.target_path)
        set_path(ctx.record, cfg.target_path, cfg.value)
        return StepResult(
            lineage=[
                self._entry(
                    target_path=cfg.target_path,
                    before_value=before,
                    after_value=cfg.value,
                    note="constant",
                )
            ]
        )


# --------------------------------------------------------------------------- #
# default (coalesce)
# --------------------------------------------------------------------------- #


class DefaultConfig(StepConfigBase):
    target_path: str
    value: Any = Field(description="Value to set only if currently missing/None.")


@registry.register
class DefaultStep(TransformStep):
    """Set a field only if it is currently missing or None (coalesce)."""

    type: ClassVar[str] = "default"
    config_model: ClassVar[type[StepConfigBase]] = DefaultConfig

    def apply(self, ctx: StepContext) -> StepResult:
        cfg: DefaultConfig = self.config  # type: ignore[assignment]
        current = get_path(ctx.record, cfg.target_path)
        if current is not None and has_path(ctx.record, cfg.target_path):
            return StepResult(
                lineage=[
                    self._entry(
                        target_path=cfg.target_path,
                        before_value=current,
                        after_value=current,
                        note="default skipped (already set)",
                    )
                ]
            )
        set_path(ctx.record, cfg.target_path, cfg.value)
        return StepResult(
            lineage=[
                self._entry(
                    target_path=cfg.target_path,
                    before_value=current,
                    after_value=cfg.value,
                    note="default applied",
                )
            ]
        )


# --------------------------------------------------------------------------- #
# cast
# --------------------------------------------------------------------------- #


class CastConfig(StepConfigBase):
    target_path: str
    to: Literal["str", "int", "float", "bool", "date"]
    date_format: str | None = Field(
        default=None, description="strptime format when to='date' (else ISO parse)."
    )


@registry.register
class CastStep(TransformStep):
    """Convert a field's type (str/int/float/bool/date)."""

    type: ClassVar[str] = "cast"
    config_model: ClassVar[type[StepConfigBase]] = CastConfig

    _TRUEISH = {"1", "true", "yes", "y", "t"}

    def _coerce(self, value: Any, cfg: CastConfig) -> Any:
        if value is None:
            return None
        if cfg.to == "str":
            return str(value)
        if cfg.to == "int":
            return int(float(value)) if isinstance(value, str) else int(value)
        if cfg.to == "float":
            return float(value)
        if cfg.to == "bool":
            return str(value).strip().lower() in self._TRUEISH if isinstance(value, str) else bool(value)
        # date
        text = str(value)
        if cfg.date_format:
            return datetime.strptime(text, cfg.date_format)
        return datetime.fromisoformat(text.replace("Z", "+00:00"))

    def apply(self, ctx: StepContext) -> StepResult:
        cfg: CastConfig = self.config  # type: ignore[assignment]
        before = get_path(ctx.record, cfg.target_path)
        after = self._coerce(before, cfg)
        set_path(ctx.record, cfg.target_path, after)
        return StepResult(
            lineage=[
                self._entry(
                    source_paths=[cfg.target_path],
                    target_path=cfg.target_path,
                    before_value=before,
                    after_value=after,
                    note=f"cast to {cfg.to}",
                )
            ]
        )


# --------------------------------------------------------------------------- #
# trim
# --------------------------------------------------------------------------- #


class TrimConfig(StepConfigBase):
    target_path: str
    strip_quotes: bool = True


@registry.register
class TrimStep(TransformStep):
    """Strip whitespace and (optionally) surrounding quotes from a string."""

    type: ClassVar[str] = "trim"
    config_model: ClassVar[type[StepConfigBase]] = TrimConfig

    def apply(self, ctx: StepContext) -> StepResult:
        cfg: TrimConfig = self.config  # type: ignore[assignment]
        before = get_path(ctx.record, cfg.target_path)
        after = before
        if isinstance(before, str):
            after = before.strip()
            if cfg.strip_quotes and len(after) >= 2 and after[0] == after[-1] and after[0] in "\"'":
                after = after[1:-1].strip()
        set_path(ctx.record, cfg.target_path, after)
        return StepResult(
            lineage=[
                self._entry(
                    source_paths=[cfg.target_path],
                    target_path=cfg.target_path,
                    before_value=before,
                    after_value=after,
                    note="trim",
                )
            ]
        )


# --------------------------------------------------------------------------- #
# lookup (map)
# --------------------------------------------------------------------------- #


class LookupConfig(StepConfigBase):
    source_path: str
    target_path: str
    table: dict[str, Any] = Field(description="Mapping of source value -> replacement.")
    keep_unmatched: bool = Field(
        default=True, description="If unmatched, keep original (True) or set None (False)."
    )


@registry.register
class LookupStep(TransformStep):
    """Replace a value via a configured lookup table (e.g. league -> leagueId)."""

    type: ClassVar[str] = "lookup"
    config_model: ClassVar[type[StepConfigBase]] = LookupConfig

    def apply(self, ctx: StepContext) -> StepResult:
        cfg: LookupConfig = self.config  # type: ignore[assignment]
        source_value = get_path(ctx.record, cfg.source_path)
        key = str(source_value)
        if key in cfg.table:
            after = cfg.table[key]
            note = "lookup matched"
        else:
            after = source_value if cfg.keep_unmatched else None
            note = "lookup unmatched"
        before = get_path(ctx.record, cfg.target_path)
        set_path(ctx.record, cfg.target_path, after)
        return StepResult(
            lineage=[
                self._entry(
                    source_paths=[cfg.source_path],
                    target_path=cfg.target_path,
                    before_value=before,
                    after_value=after,
                    note=note,
                )
            ]
        )


# --------------------------------------------------------------------------- #
# concat
# --------------------------------------------------------------------------- #


class ConcatConfig(StepConfigBase):
    source_paths: list[str] = Field(min_length=1)
    target_path: str
    separator: str = " "
    skip_none: bool = True


@registry.register
class ConcatStep(TransformStep):
    """Join multiple source fields into one target field."""

    type: ClassVar[str] = "concat"
    config_model: ClassVar[type[StepConfigBase]] = ConcatConfig

    def apply(self, ctx: StepContext) -> StepResult:
        cfg: ConcatConfig = self.config  # type: ignore[assignment]
        values = [get_path(ctx.record, p) for p in cfg.source_paths]
        parts = [str(v) for v in values if not (cfg.skip_none and v is None)]
        after = cfg.separator.join(parts)
        before = get_path(ctx.record, cfg.target_path)
        set_path(ctx.record, cfg.target_path, after)
        return StepResult(
            lineage=[
                self._entry(
                    source_paths=cfg.source_paths,
                    target_path=cfg.target_path,
                    before_value=before,
                    after_value=after,
                    note=f"concat with {cfg.separator!r}",
                )
            ]
        )


# --------------------------------------------------------------------------- #
# split
# --------------------------------------------------------------------------- #


class SplitConfig(StepConfigBase):
    source_path: str
    target_paths: list[str] = Field(min_length=1)
    separator: str = " "


@registry.register
class SplitStep(TransformStep):
    """Split one source field into many target fields."""

    type: ClassVar[str] = "split"
    config_model: ClassVar[type[StepConfigBase]] = SplitConfig

    def apply(self, ctx: StepContext) -> StepResult:
        cfg: SplitConfig = self.config  # type: ignore[assignment]
        source_value = get_path(ctx.record, cfg.source_path)
        parts = str(source_value).split(cfg.separator) if source_value is not None else []
        entries = []
        for idx, target in enumerate(cfg.target_paths):
            after = parts[idx] if idx < len(parts) else None
            before = get_path(ctx.record, target)
            set_path(ctx.record, target, after)
            entries.append(
                self._entry(
                    source_paths=[cfg.source_path],
                    target_path=target,
                    before_value=before,
                    after_value=after,
                    note=f"split[{idx}]",
                )
            )
        return StepResult(lineage=entries)


# --------------------------------------------------------------------------- #
# drop
# --------------------------------------------------------------------------- #


class DropConfig(StepConfigBase):
    target_path: str


@registry.register
class DropStep(TransformStep):
    """Remove a field from the record."""

    type: ClassVar[str] = "drop"
    config_model: ClassVar[type[StepConfigBase]] = DropConfig

    def apply(self, ctx: StepContext) -> StepResult:
        cfg: DropConfig = self.config  # type: ignore[assignment]
        before = delete_path(ctx.record, cfg.target_path)
        return StepResult(
            lineage=[
                self._entry(
                    source_paths=[cfg.target_path],
                    target_path=cfg.target_path,
                    before_value=before,
                    after_value=None,
                    note="dropped field",
                )
            ]
        )


# --------------------------------------------------------------------------- #
# filter
# --------------------------------------------------------------------------- #


class FilterConfig(StepConfigBase):
    target_path: str
    op: Literal["eq", "ne", "in", "not_in", "exists", "not_exists", "gt", "lt"]
    value: Any = None
    # action: keep the record when the predicate is True, or drop it when True.
    mode: Literal["keep_if", "drop_if"] = "keep_if"


@registry.register
class FilterStep(TransformStep):
    """Keep or discard the whole record by a predicate (records the reason)."""

    type: ClassVar[str] = "filter"
    config_model: ClassVar[type[StepConfigBase]] = FilterConfig

    def _predicate(self, ctx: StepContext, cfg: FilterConfig) -> bool:
        value = get_path(ctx.record, cfg.target_path)
        match cfg.op:
            case "eq":
                return value == cfg.value
            case "ne":
                return value != cfg.value
            case "in":
                return value in (cfg.value or [])
            case "not_in":
                return value not in (cfg.value or [])
            case "exists":
                return has_path(ctx.record, cfg.target_path) and value is not None
            case "not_exists":
                return not has_path(ctx.record, cfg.target_path) or value is None
            case "gt":
                return value is not None and value > cfg.value
            case "lt":
                return value is not None and value < cfg.value
        return True

    def apply(self, ctx: StepContext) -> StepResult:
        cfg: FilterConfig = self.config  # type: ignore[assignment]
        predicate = self._predicate(ctx, cfg)
        # keep_if: drop when predicate False. drop_if: drop when predicate True.
        dropped = (not predicate) if cfg.mode == "keep_if" else predicate
        reason = (
            f"filter {cfg.mode} {cfg.target_path} {cfg.op} {cfg.value!r} -> "
            f"{'dropped' if dropped else 'kept'}"
        )
        return StepResult(
            lineage=[
                self._entry(
                    source_paths=[cfg.target_path],
                    target_path=None,
                    before_value=get_path(ctx.record, cfg.target_path),
                    after_value=None,
                    note=reason,
                )
            ],
            dropped=dropped,
            drop_reason=reason if dropped else None,
        )
