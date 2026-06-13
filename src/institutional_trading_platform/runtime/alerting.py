"""Alert manager for Phase 7 dashboard and shadow-run operations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .audit_store import InMemoryAuditStore
from .event_bus import EventBus, RuntimeEvent, RuntimeEventType


class AlertType(StrEnum):
    ZERODHA_DISCONNECTED = "ZERODHA_DISCONNECTED"
    AUTH_FAILED = "AUTH_FAILED"
    STALE_FEED = "STALE_FEED"
    MALFORMED_TICK_SPIKE = "MALFORMED_TICK_SPIKE"
    RECONCILIATION_FAILED = "RECONCILIATION_FAILED"
    UNEXPECTED_BROKER_POSITION = "UNEXPECTED_BROKER_POSITION"
    RISK_BLOCK = "RISK_BLOCK"
    KILL_SWITCH_ACTIVE = "KILL_SWITCH_ACTIVE"
    APPROVAL_PENDING = "APPROVAL_PENDING"
    EXIT_SUGGESTED = "EXIT_SUGGESTED"
    PAPER_DRAWDOWN_BREACH = "PAPER_DRAWDOWN_BREACH"
    DAILY_LOSS_BREACH = "DAILY_LOSS_BREACH"


@dataclass(frozen=True)
class RuntimeAlert:
    alert_type: AlertType
    severity: str
    message: str
    source_event_id: str | None = None


class AlertManager:
    """Emit operational alerts as audit-store events."""

    def __init__(self, event_bus: EventBus, audit_store: InMemoryAuditStore) -> None:
        self.event_bus = event_bus
        self.audit_store = audit_store

    def handle_event(self, event: RuntimeEvent) -> RuntimeAlert | None:
        alert = self._alert_for(event)
        if alert is None:
            return None
        alert_event = RuntimeEvent(RuntimeEventType.ALERT_EMITTED, event.symbol, {"alert_type": alert.alert_type.value, "severity": alert.severity, "message": alert.message, "source_event_id": alert.source_event_id}, event.correlation_id)
        self.event_bus.publish(alert_event)
        if not any(stored.event_id == alert_event.event_id for stored in self.audit_store.all_events()):
            self.audit_store.append(alert_event)
        return alert

    @staticmethod
    def _alert_for(event: RuntimeEvent) -> RuntimeAlert | None:
        if event.event_type == RuntimeEventType.ZERODHA_DISCONNECTED:
            return RuntimeAlert(AlertType.ZERODHA_DISCONNECTED, "HIGH", "Zerodha disconnected", event.event_id)
        if event.event_type == RuntimeEventType.ZERODHA_AUTH_FAILED:
            return RuntimeAlert(AlertType.AUTH_FAILED, "HIGH", "Zerodha authentication failed", event.event_id)
        if event.event_type == RuntimeEventType.BROKER_RECONCILIATION_FAILED:
            reasons = tuple(str(reason) for reason in event.payload.get("reasons", ()))
            alert_type = AlertType.UNEXPECTED_BROKER_POSITION if any("unexpected open position" in reason for reason in reasons) else AlertType.RECONCILIATION_FAILED
            return RuntimeAlert(alert_type, "CRITICAL", "Broker reconciliation failed", event.event_id)
        if event.event_type == RuntimeEventType.RISK_BLOCKED:
            reasons = " ".join(str(reason) for reason in event.payload.get("reasons", ()))
            if "stale" in reasons.lower():
                return RuntimeAlert(AlertType.STALE_FEED, "HIGH", "Market data feed is stale", event.event_id)
            if "kill switch" in reasons.lower():
                return RuntimeAlert(AlertType.KILL_SWITCH_ACTIVE, "CRITICAL", "Kill switch active", event.event_id)
            if "daily loss" in reasons.lower():
                return RuntimeAlert(AlertType.DAILY_LOSS_BREACH, "CRITICAL", "Daily loss limit breached", event.event_id)
            return RuntimeAlert(AlertType.RISK_BLOCK, "MEDIUM", "Risk block emitted", event.event_id)
        if event.event_type == RuntimeEventType.INSTRUMENT_RESOLUTION_FAILED:
            return RuntimeAlert(AlertType.MALFORMED_TICK_SPIKE, "MEDIUM", "Malformed or unresolved tick/instrument incident", event.event_id)
        if event.event_type == RuntimeEventType.TRADE_APPROVAL_REQUESTED:
            return RuntimeAlert(AlertType.APPROVAL_PENDING, "MEDIUM", "Trade approval pending", event.event_id)
        if event.event_type == RuntimeEventType.EXIT_SUGGESTED:
            return RuntimeAlert(AlertType.EXIT_SUGGESTED, "HIGH", "Exit suggested for approved plan", event.event_id)
        if event.event_type == RuntimeEventType.PAPER_PNL_UPDATED and float(event.payload.get("drawdown_pct", 0.0) or 0.0) > 0:
            return RuntimeAlert(AlertType.PAPER_DRAWDOWN_BREACH, "HIGH", "Paper drawdown threshold breached", event.event_id)
        return None
