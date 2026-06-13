"""In-memory event bus for ALPHA-GATE X runtime events."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Callable
from uuid import uuid4


class RuntimeEventType(StrEnum):
    TICK_RECEIVED = "TickReceived"
    CANDLE_FINALIZED = "CandleFinalized"
    SIGNAL_GENERATED = "SignalGenerated"
    RISK_BLOCKED = "RiskBlocked"
    PAPER_ORDER_CREATED = "PaperOrderCreated"
    PAPER_ORDER_FILLED = "PaperOrderFilled"
    PAPER_POSITION_OPENED = "PaperPositionOpened"
    PAPER_POSITION_CLOSED = "PaperPositionClosed"
    PAPER_PNL_UPDATED = "PaperPnLUpdated"
    RUNTIME_HEARTBEAT = "RuntimeHeartbeat"
    RUNTIME_ERROR = "RuntimeError"
    ZERODHA_CONNECTED = "ZerodhaConnected"
    ZERODHA_DISCONNECTED = "ZerodhaDisconnected"
    ZERODHA_AUTH_FAILED = "ZerodhaAuthFailed"
    ZERODHA_TICK_RECEIVED = "ZerodhaTickReceived"
    INSTRUMENT_RESOLVED = "InstrumentResolved"
    INSTRUMENT_RESOLUTION_FAILED = "InstrumentResolutionFailed"
    BROKER_RECONCILIATION_PASSED = "BrokerReconciliationPassed"
    BROKER_RECONCILIATION_FAILED = "BrokerReconciliationFailed"
    TRADE_APPROVAL_REQUESTED = "TradeApprovalRequested"
    TRADE_APPROVED = "TradeApproved"
    TRADE_REJECTED = "TradeRejected"
    ZERODHA_ORDER_PREVIEW_GENERATED = "ZerodhaOrderPreviewGenerated"
    REAL_ORDER_BLOCKED = "RealOrderBlocked"
    EXIT_SUGGESTED = "ExitSuggested"
    ALERT_EMITTED = "AlertEmitted"
    RUNTIME_PERSISTENCE_FAILED = "RuntimePersistenceFailed"
    RECOVERY_STARTED = "RecoveryStarted"
    RECOVERY_COMPLETED = "RecoveryCompleted"
    RECOVERY_FAILED = "RecoveryFailed"
    UNSAFE_ACTION_BLOCKED = "UnsafeActionBlocked"


@dataclass(frozen=True)
class RuntimeEvent:
    event_type: RuntimeEventType
    symbol: str | None = None
    payload: dict[str, object] = field(default_factory=dict)
    correlation_id: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    event_id: str = field(default_factory=lambda: f"evt-{uuid4()}")
    source: str = "runtime"
    severity: str = "INFO"


class EventBus:
    """Synchronous in-memory pub/sub bus used by the paper runtime."""

    def __init__(self) -> None:
        self.events: list[RuntimeEvent] = []
        self._subscribers: list[Callable[[RuntimeEvent], None]] = []

    def subscribe(self, handler: Callable[[RuntimeEvent], None]) -> None:
        self._subscribers.append(handler)

    def publish(self, event: RuntimeEvent) -> RuntimeEvent:
        self.events.append(event)
        for handler in self._subscribers:
            handler(event)
        return event
