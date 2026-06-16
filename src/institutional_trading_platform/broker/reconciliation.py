"""Broker ground-truth reconciliation for Phase 6 approval-mode safety."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..runtime.event_bus import EventBus, RuntimeEvent, RuntimeEventType


@dataclass(frozen=True)
class BrokerPositionSnapshot:
    symbol: str
    quantity: int
    average_price: float


@dataclass(frozen=True)
class BrokerOrderSnapshot:
    order_id: str
    correlation_id: str
    symbol: str
    status: str
    quantity: int


@dataclass(frozen=True)
class BrokerTradeSnapshot:
    order_id: str
    symbol: str
    quantity: int
    average_price: float


@dataclass(frozen=True)
class BrokerStateSnapshot:
    positions: tuple[BrokerPositionSnapshot, ...] = ()
    holdings: tuple[BrokerPositionSnapshot, ...] = ()
    orders: tuple[BrokerOrderSnapshot, ...] = ()
    trades: tuple[BrokerTradeSnapshot, ...] = ()
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class LocalApprovalState:
    positions: tuple[BrokerPositionSnapshot, ...] = ()
    orders: tuple[BrokerOrderSnapshot, ...] = ()


@dataclass(frozen=True)
class ReconciliationResult:
    passed: bool
    reasons: tuple[str, ...]


class BrokerReconciliationService:
    """Compare broker ground truth with local paper/approval state."""

    def __init__(self, event_bus: EventBus | None = None, stale_after_seconds: int = 30) -> None:
        self.event_bus = event_bus
        self.stale_after_seconds = stale_after_seconds
        self.last_result = ReconciliationResult(False, ("reconciliation not run",))

    def reconcile(self, broker: BrokerStateSnapshot, local: LocalApprovalState, now: datetime | None = None) -> ReconciliationResult:
        now = now or datetime.now(timezone.utc)
        reasons: list[str] = []
        if broker.updated_at.tzinfo is None:
            reasons.append("stale broker state")
        elif (now - broker.updated_at).total_seconds() > self.stale_after_seconds:
            reasons.append("stale broker state")
        broker_positions = {item.symbol: item for item in broker.positions}
        local_positions = {item.symbol: item for item in local.positions}
        for symbol, broker_position in broker_positions.items():
            local_position = local_positions.get(symbol)
            if local_position is None and broker_position.quantity != 0:
                reasons.append(f"unexpected open position {symbol}")
                continue
            if local_position is not None:
                if broker_position.quantity != local_position.quantity:
                    reasons.append(f"quantity mismatch {symbol}")
                if abs(broker_position.average_price - local_position.average_price) > 0.01:
                    reasons.append(f"average price mismatch {symbol}")
        broker_orders = {item.correlation_id: item for item in broker.orders}
        for local_order in local.orders:
            broker_order = broker_orders.get(local_order.correlation_id)
            if broker_order is None:
                reasons.append(f"missing order {local_order.correlation_id}")
            elif broker_order.status.upper() == "REJECTED":
                reasons.append(f"rejected order {local_order.correlation_id}")
        self.last_result = ReconciliationResult(not reasons, tuple(reasons))
        if self.event_bus is not None:
            event_type = RuntimeEventType.BROKER_RECONCILIATION_PASSED if self.last_result.passed else RuntimeEventType.BROKER_RECONCILIATION_FAILED
            self.event_bus.publish(RuntimeEvent(event_type, payload={"reasons": self.last_result.reasons}))
        return self.last_result
