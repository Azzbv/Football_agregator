"""In-process domain events for raw-ingest decoupling.

Optional internal decoupling per the design: when a batch of raw records lands,
the runner publishes a :class:`RawIngested` event. The unification context
subscribes and reacts (raw -> unified) without the ingestion package importing
unification. This keeps the two contexts decoupled while staying in-process — no
Kafka, just a tiny async pub/sub.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from fdp_shared.domain import SourceName
from fdp_shared.logging import get_logger

from fdp_ingestion.ports import RawRecord

logger = get_logger(__name__)


@dataclass(frozen=True)
class RawIngested:
    """Emitted after a source's raw records are persisted.

    ``records`` carries the in-memory :class:`RawRecord` objects that were just
    written, so a consumer (unification) can map them directly without reading
    them back out of Mongo. ``source_refs`` is kept as a lightweight identifier
    list and a replay fallback: a consumer that receives an event with empty
    ``records`` (e.g. a persisted/outbox event) can re-query by refs instead.
    """

    source: SourceName
    entity: str
    source_refs: tuple[str, ...]
    records: tuple[RawRecord, ...] = field(default_factory=tuple)


Handler = Callable[[RawIngested], Awaitable[None]]


class EventBus:
    """Minimal async in-process publish/subscribe bus."""

    def __init__(self) -> None:
        self._handlers: list[Handler] = []

    def subscribe(self, handler: Handler) -> None:
        self._handlers.append(handler)

    async def publish(self, event: RawIngested) -> None:
        logger.debug("event_published", source=event.source, entity=event.entity)
        for handler in self._handlers:
            await handler(event)
