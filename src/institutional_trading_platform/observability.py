"""Structured audit, monitoring, and health primitives."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Mapping


class Severity(StrEnum):
    """Operational event severity."""

    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class AuditEvent:
    """Append-only audit event for research, risk, execution, and governance."""

    event_type: str
    actor: str
    severity: Severity
    message: str
    metadata: Mapping[str, str] = field(default_factory=dict)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.event_type.strip() or not self.actor.strip() or not self.message.strip():
            raise ValueError("event_type, actor, and message are required")
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")

    def to_log_record(self) -> dict[str, object]:
        """Serialize to a structured logging payload."""

        return {
            "timestamp": self.occurred_at.isoformat(),
            "severity": self.severity.value,
            "event_type": self.event_type,
            "actor": self.actor,
            "message": self.message,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class HealthCheck:
    """Single component health probe result."""

    component: str
    healthy: bool
    latency_ms: float
    message: str = ""

    def __post_init__(self) -> None:
        if not self.component.strip():
            raise ValueError("component is required")
        if self.latency_ms < 0:
            raise ValueError("latency_ms cannot be negative")


@dataclass(frozen=True)
class SystemHealth:
    """Aggregated platform health state."""

    checks: tuple[HealthCheck, ...]
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def healthy(self) -> bool:
        """Whether all components are healthy."""

        return all(check.healthy for check in self.checks)

    @property
    def degraded_components(self) -> tuple[str, ...]:
        """Names of unhealthy components."""

        return tuple(check.component for check in self.checks if not check.healthy)

    @property
    def max_latency_ms(self) -> float:
        """Maximum observed component latency."""

        return max((check.latency_ms for check in self.checks), default=0.0)
