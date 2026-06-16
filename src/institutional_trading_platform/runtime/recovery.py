"""Crash recovery service for Phase 8 durable runtime state."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .event_bus import EventBus, RuntimeEvent, RuntimeEventType
from .persistence import PersistenceUnavailable, RuntimeStateSnapshot, SQLiteAuditStore


class RecoveryMode(StrEnum):
    RECOVERED = "RECOVERED"
    SAFE_RECOVERY = "SAFE_RECOVERY"


@dataclass(frozen=True)
class RecoveryStatus:
    mode: RecoveryMode
    snapshot: RuntimeStateSnapshot | None
    unresolved_approvals: int
    open_approved_plans: int
    reasons: tuple[str, ...] = ()

    @property
    def trading_blocked(self) -> bool:
        return self.mode == RecoveryMode.SAFE_RECOVERY


class CrashRecoveryService:
    """Restore durable state and require reconciliation before new approvals."""

    def __init__(self, audit_store: SQLiteAuditStore, event_bus: EventBus | None = None) -> None:
        self.audit_store = audit_store
        self.event_bus = event_bus
        self.last_status = RecoveryStatus(RecoveryMode.SAFE_RECOVERY, None, 0, 0, ("recovery not run",))

    def recover(self, *, reconciliation_passed: bool) -> RecoveryStatus:
        self._emit(RuntimeEventType.RECOVERY_STARTED, {"message": "recovery started"})
        try:
            snapshot = self.audit_store.latest_snapshot()
            pending = self.audit_store.by_event_type(RuntimeEventType.TRADE_APPROVAL_REQUESTED)
            approved = self.audit_store.by_event_type(RuntimeEventType.TRADE_APPROVED)
            exits = self.audit_store.by_event_type(RuntimeEventType.EXIT_SUGGESTED)
            reasons: list[str] = []
            if snapshot is None:
                reasons.append("no runtime snapshot found")
            if not reconciliation_passed:
                reasons.append("broker reconciliation required before new approval requests")
            if snapshot is not None and snapshot.current_mode == RecoveryMode.SAFE_RECOVERY.value:
                reasons.append("previous runtime was in SAFE_RECOVERY")
            mode = RecoveryMode.SAFE_RECOVERY if reasons else RecoveryMode.RECOVERED
            self.last_status = RecoveryStatus(mode, snapshot, len(pending), max(0, len(approved) - len(exits)), tuple(reasons))
            self._emit(RuntimeEventType.RECOVERY_COMPLETED if mode == RecoveryMode.RECOVERED else RuntimeEventType.RECOVERY_FAILED, {"mode": mode.value, "reasons": self.last_status.reasons})
            return self.last_status
        except PersistenceUnavailable as exc:
            self.last_status = RecoveryStatus(RecoveryMode.SAFE_RECOVERY, None, 0, 0, (str(exc),))
            self._emit(RuntimeEventType.RECOVERY_FAILED, {"mode": RecoveryMode.SAFE_RECOVERY.value, "reasons": self.last_status.reasons})
            return self.last_status

    def _emit(self, event_type: RuntimeEventType, payload: dict[str, object]) -> None:
        if self.event_bus is not None:
            self.event_bus.publish(RuntimeEvent(event_type, payload=payload, source="recovery"))
