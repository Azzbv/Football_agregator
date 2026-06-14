"""Dot-path get/set/delete helpers for the working record.

The working record is a plain ``dict[str, Any]``. Steps address fields with
dot-paths (``a.b.c``); these helpers create intermediate dicts on set and treat
a missing leaf as ``None`` on get. JSONPath (read-only, richer queries) is
handled separately in the ``extract`` step via jsonpath-ng; everything else uses
these simple, predictable dot-paths.
"""

from __future__ import annotations

from typing import Any

_MISSING = object()


def get_path(record: dict[str, Any], path: str) -> Any:
    """Return the value at ``path`` or ``None`` if any segment is missing."""

    current: Any = record
    for segment in path.split("."):
        if isinstance(current, dict) and segment in current:
            current = current[segment]
        else:
            return None
    return current


def has_path(record: dict[str, Any], path: str) -> bool:
    """True if every segment of ``path`` exists (leaf may be ``None``)."""

    current: Any = record
    for segment in path.split("."):
        if isinstance(current, dict) and segment in current:
            current = current[segment]
        else:
            return False
    return True


def set_path(record: dict[str, Any], path: str, value: Any) -> None:
    """Set ``path`` to ``value``, creating intermediate dicts as needed."""

    segments = path.split(".")
    current = record
    for segment in segments[:-1]:
        nxt = current.get(segment)
        if not isinstance(nxt, dict):
            nxt = {}
            current[segment] = nxt
        current = nxt
    current[segments[-1]] = value


def delete_path(record: dict[str, Any], path: str) -> Any:
    """Delete ``path`` if present; return the removed value or ``None``."""

    segments = path.split(".")
    current: Any = record
    for segment in segments[:-1]:
        if not isinstance(current, dict) or segment not in current:
            return None
        current = current[segment]
    if isinstance(current, dict):
        return current.pop(segments[-1], None)
    return None
