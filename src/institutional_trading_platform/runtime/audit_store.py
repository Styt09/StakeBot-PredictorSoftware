"""In-memory runtime audit store for Phase 5."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime

from .event_bus import RuntimeEvent, RuntimeEventType


class InMemoryAuditStore:
    """Append-only audit store with simple runtime queries."""

    def __init__(self) -> None:
        self._events: list[RuntimeEvent] = []

    def append(self, event: RuntimeEvent) -> None:
        self._events.append(event)

    def all_events(self) -> tuple[RuntimeEvent, ...]:
        return tuple(self._events)

    def by_correlation_id(self, correlation_id: str) -> tuple[RuntimeEvent, ...]:
        return tuple(event for event in self._events if event.correlation_id == correlation_id)

    def by_symbol(self, symbol: str) -> tuple[RuntimeEvent, ...]:
        return tuple(event for event in self._events if event.symbol == symbol)

    def by_event_type(self, event_type: RuntimeEventType) -> tuple[RuntimeEvent, ...]:
        return tuple(event for event in self._events if event.event_type == event_type)

    def export_json(self) -> str:
        def clean(value: object) -> object:
            if isinstance(value, datetime):
                return value.isoformat()
            if isinstance(value, RuntimeEventType):
                return value.value
            if hasattr(value, "value"):
                return getattr(value, "value")
            if isinstance(value, dict):
                return {key: clean(item) for key, item in value.items()}
            if isinstance(value, (tuple, list)):
                return [clean(item) for item in value]
            return value

        return json.dumps([clean(asdict(event)) for event in self._events], indent=2, sort_keys=True)
