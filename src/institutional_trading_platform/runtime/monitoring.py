"""Enterprise monitoring, metrics, and incident management for Phase 17."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4

from .audit_store import InMemoryAuditStore
from .event_bus import RuntimeEvent, RuntimeEventType


class IncidentSeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class IncidentStatus(StrEnum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"


class AlertRouteType(StrEnum):
    CONSOLE = "CONSOLE"
    AUDIT_STORE = "AUDIT_STORE"
    WEBHOOK_PLACEHOLDER = "WEBHOOK_PLACEHOLDER"


@dataclass(frozen=True)
class MetricSample:
    name: str
    value: float
    labels: dict[str, str] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, object]:
        return {"name": self.name, "value": self.value, "labels": self.labels, "timestamp": self.timestamp.isoformat()}


class MetricsRegistry:
    """Small dependency-free registry for shadow/paper monitoring metrics."""

    DEFAULT_METRICS = (
        "runtime_uptime_seconds",
        "zerodha_auth_status",
        "websocket_freshness_seconds",
        "tick_ingestion_rate",
        "candle_finalization_rate",
        "signal_generation_rate",
        "approval_request_rate",
        "preview_generation_rate",
        "blocked_real_order_attempts",
        "reconciliation_pass_rate",
        "reconciliation_fail_rate",
        "stale_feed_incidents",
        "malformed_tick_incidents",
        "persistence_failures",
        "recovery_events",
        "api_request_latency_ms",
        "shadow_run_progress_pct",
        "strategy_health_score",
        "portfolio_exposure_pct",
        "options_greeks_exposure",
        "execution_quality_score",
        "ml_research_advisory_status",
    )

    def __init__(self) -> None:
        self._samples: dict[str, list[MetricSample]] = {name: [] for name in self.DEFAULT_METRICS}

    def record(self, name: str, value: float, *, labels: dict[str, str] | None = None, timestamp: datetime | None = None) -> MetricSample:
        sample = MetricSample(name=name, value=float(value), labels=labels or {}, timestamp=timestamp or datetime.now(timezone.utc))
        self._samples.setdefault(name, []).append(sample)
        return sample

    def latest(self, name: str) -> MetricSample | None:
        samples = self._samples.get(name, [])
        return samples[-1] if samples else None

    def snapshot(self) -> dict[str, object]:
        return {
            "metrics": {name: sample.to_dict() for name, samples in self._samples.items() if samples for sample in [samples[-1]]},
            "registered_metrics": tuple(self._samples),
            "go_live_allowed": False,
        }

    def export_json(self) -> str:
        return json.dumps(self.snapshot(), indent=2, sort_keys=True)

    def export_prometheus(self) -> str:
        lines: list[str] = []
        for name, samples in sorted(self._samples.items()):
            if not samples:
                continue
            sample = samples[-1]
            label_text = ""
            if sample.labels:
                label_text = "{" + ",".join(f'{key}="{value}"' for key, value in sorted(sample.labels.items())) + "}"
            lines.append(f"# TYPE {name} gauge")
            lines.append(f"{name}{label_text} {sample.value}")
        return "\n".join(lines)


@dataclass(frozen=True)
class Incident:
    incident_id: str
    incident_type: str
    severity: IncidentSeverity
    status: IncidentStatus
    created_at: datetime
    affected_symbols: tuple[str, ...] = ()
    correlation_id: str | None = None
    runbook_section: str = "Phase 17 incident response"
    recommended_action: str = "Investigate and keep trading decisions blocked until resolved."
    resolved_at: datetime | None = None
    message: str = ""
    go_live_allowed: bool = False

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["severity"] = self.severity.value
        data["status"] = self.status.value
        data["created_at"] = self.created_at.isoformat()
        data["resolved_at"] = self.resolved_at.isoformat() if self.resolved_at else None
        data["go_live_allowed"] = False
        return data


class IncidentManager:
    """Track incidents and lifecycle transitions."""

    def __init__(self) -> None:
        self._incidents: dict[str, Incident] = {}

    def create(self, incident_type: str, severity: IncidentSeverity, *, affected_symbols: tuple[str, ...] = (), correlation_id: str | None = None, runbook_section: str = "Phase 17 incident response", recommended_action: str = "Follow runbook and block new approvals if critical.", message: str = "", now: datetime | None = None) -> Incident:
        incident = Incident(
            incident_id=f"inc-{uuid4()}",
            incident_type=incident_type,
            severity=severity,
            status=IncidentStatus.OPEN,
            created_at=now or datetime.now(timezone.utc),
            affected_symbols=affected_symbols,
            correlation_id=correlation_id,
            runbook_section=runbook_section,
            recommended_action=recommended_action,
            message=message,
            go_live_allowed=False,
        )
        self._incidents[incident.incident_id] = incident
        return incident

    def acknowledge(self, incident_id: str, *, now: datetime | None = None) -> Incident:
        incident = self._incidents[incident_id]
        updated = Incident(**{**incident.__dict__, "status": IncidentStatus.ACKNOWLEDGED})
        self._incidents[incident_id] = updated
        return updated

    def resolve(self, incident_id: str, *, now: datetime | None = None) -> Incident:
        incident = self._incidents[incident_id]
        updated = Incident(**{**incident.__dict__, "status": IncidentStatus.RESOLVED, "resolved_at": now or datetime.now(timezone.utc)})
        self._incidents[incident_id] = updated
        return updated

    def all(self) -> tuple[Incident, ...]:
        return tuple(self._incidents.values())

    def open_incidents(self) -> tuple[Incident, ...]:
        return tuple(incident for incident in self._incidents.values() if incident.status != IncidentStatus.RESOLVED)

    def unresolved_critical(self) -> tuple[Incident, ...]:
        return tuple(incident for incident in self.open_incidents() if incident.severity == IncidentSeverity.CRITICAL)


@dataclass(frozen=True)
class AlertRouteResult:
    route_type: AlertRouteType
    delivered: bool
    message: str
    go_live_allowed: bool = False

    def to_dict(self) -> dict[str, object]:
        return {"route_type": self.route_type.value, "delivered": self.delivered, "message": self.message, "go_live_allowed": False}


class AlertRouter:
    """Route alerts locally. Webhook delivery is a disabled placeholder by default."""

    def __init__(self, *, audit_store: InMemoryAuditStore | None = None, console_enabled: bool = True, audit_enabled: bool = True, webhook_enabled: bool = False) -> None:
        self.audit_store = audit_store
        self.console_enabled = console_enabled
        self.audit_enabled = audit_enabled
        self.webhook_enabled = webhook_enabled
        self._results: list[AlertRouteResult] = []

    @property
    def configured_for_manual_review(self) -> bool:
        return self.console_enabled or (self.audit_enabled and self.audit_store is not None)

    def route(self, incident: Incident) -> tuple[AlertRouteResult, ...]:
        results: list[AlertRouteResult] = []
        if self.console_enabled:
            results.append(AlertRouteResult(AlertRouteType.CONSOLE, True, f"{incident.severity.value}: {incident.incident_type}"))
        if self.audit_enabled and self.audit_store is not None:
            self.audit_store.append(RuntimeEvent(RuntimeEventType.ALERT_EMITTED, symbol=incident.affected_symbols[0] if incident.affected_symbols else None, correlation_id=incident.correlation_id, payload={"incident": incident.to_dict()}, severity=incident.severity.value, source="monitoring"))
            results.append(AlertRouteResult(AlertRouteType.AUDIT_STORE, True, "stored in audit log"))
        results.append(AlertRouteResult(AlertRouteType.WEBHOOK_PLACEHOLDER, False if not self.webhook_enabled else True, "webhook disabled by default" if not self.webhook_enabled else "webhook placeholder enabled"))
        self._results.extend(results)
        return tuple(results)

    def results(self) -> tuple[AlertRouteResult, ...]:
        return tuple(self._results)


@dataclass(frozen=True)
class SLOTargetConfig:
    uptime_target_pct: float = 99.0
    feed_freshness_target_seconds: float = 5.0
    persistence_availability_target_pct: float = 99.0
    reconciliation_freshness_target_seconds: float = 60.0
    api_latency_target_ms: float = 500.0
    recovery_time_objective_seconds: float = 300.0


@dataclass(frozen=True)
class SLOStatus:
    uptime_ok: bool
    feed_freshness_ok: bool
    persistence_available: bool
    reconciliation_freshness_ok: bool
    api_latency_ok: bool
    recovery_time_ok: bool
    failure_reasons: tuple[str, ...]
    go_live_allowed: bool = False

    @property
    def targets_acceptable(self) -> bool:
        return not self.failure_reasons

    def to_dict(self) -> dict[str, object]:
        return {**asdict(self), "targets_acceptable": self.targets_acceptable, "go_live_allowed": False}


class SLOTracker:
    def __init__(self, config: SLOTargetConfig | None = None) -> None:
        self.config = config or SLOTargetConfig()

    def evaluate(self, *, uptime_pct: float, feed_freshness_seconds: float, persistence_available_pct: float, reconciliation_freshness_seconds: float, api_latency_ms: float, recovery_time_seconds: float) -> SLOStatus:
        checks = {
            "uptime_ok": uptime_pct >= self.config.uptime_target_pct,
            "feed_freshness_ok": feed_freshness_seconds <= self.config.feed_freshness_target_seconds,
            "persistence_available": persistence_available_pct >= self.config.persistence_availability_target_pct,
            "reconciliation_freshness_ok": reconciliation_freshness_seconds <= self.config.reconciliation_freshness_target_seconds,
            "api_latency_ok": api_latency_ms <= self.config.api_latency_target_ms,
            "recovery_time_ok": recovery_time_seconds <= self.config.recovery_time_objective_seconds,
        }
        failures = tuple(name for name, ok in checks.items() if not ok)
        return SLOStatus(**checks, failure_reasons=failures, go_live_allowed=False)


def monitoring_evidence_section(metrics: MetricsRegistry | None = None, incident_manager: IncidentManager | None = None, slo_status: SLOStatus | None = None, alert_router: AlertRouter | None = None) -> dict[str, object]:
    metrics_snapshot = metrics.snapshot() if metrics is not None else {"data_status": "DATA_UNAVAILABLE", "go_live_allowed": False}
    incidents = incident_manager.all() if incident_manager is not None else ()
    unresolved = incident_manager.unresolved_critical() if incident_manager is not None else ()
    alerts = alert_router.results() if alert_router is not None else ()
    routing_configured = alert_router.configured_for_manual_review if alert_router is not None else True
    slo = slo_status or SLOStatus(True, True, True, True, True, True, (), False)
    readiness = bool(not unresolved and slo.targets_acceptable and routing_configured)
    return {
        "metrics_snapshot": metrics_snapshot,
        "incidents": tuple(incident.to_dict() for incident in incidents),
        "alerts": tuple(result.to_dict() for result in alerts),
        "slo_status": slo.to_dict(),
        "unresolved_critical_incidents": tuple(incident.to_dict() for incident in unresolved),
        "alert_routing_configured": routing_configured,
        "monitoring_readiness": readiness,
        "go_live_allowed": False,
    }
