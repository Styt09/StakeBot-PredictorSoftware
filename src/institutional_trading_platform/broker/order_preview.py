"""Real-order safety wrapper for Zerodha order previews only."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import uuid4

from ..alpha_gate_x import AlphaSignal
from ..runtime.event_bus import EventBus, RuntimeEvent, RuntimeEventType
from ..runtime.persistence import SQLiteAuditStore


class RealOrderSafetyStatus(StrEnum):
    PREVIEW_GENERATED = "PREVIEW_GENERATED"
    NO_REAL_ORDER_PLACED = "NO_REAL_ORDER_PLACED"
    TEST_ORDER_PLACED = "TEST_ORDER_PLACED"


@dataclass(frozen=True)
class ZerodhaOrderPreview:
    correlation_id: str
    symbol: str
    exchange: str
    side: AlphaSignal
    quantity: int
    order_type: str
    product: str
    price: float | None
    stop_loss: float | None
    target: float | None
    risk_amount: float


@dataclass(frozen=True)
class RealOrderResult:
    status: RealOrderSafetyStatus
    preview: ZerodhaOrderPreview
    broker_order_id: str | None = None
    reason: str | None = None


class ZerodhaOrderSafetyWrapper:
    """Generate order previews and block real orders by default."""

    def __init__(self, event_bus: EventBus | None = None, idempotency_store: SQLiteAuditStore | None = None) -> None:
        self.event_bus = event_bus
        self.idempotency_store = idempotency_store

    def preview(self, *, correlation_id: str | None, symbol: str, exchange: str, side: AlphaSignal, quantity: int, order_type: str = "MARKET", product: str = "MIS", price: float | None = None, stop_loss: float | None = None, target: float | None = None, risk_amount: float = 0.0) -> ZerodhaOrderPreview:
        preview = ZerodhaOrderPreview(correlation_id or f"preview-{uuid4()}", symbol, exchange, side, quantity, order_type, product, price, stop_loss, target, risk_amount)
        event = RuntimeEvent(RuntimeEventType.ZERODHA_ORDER_PREVIEW_GENERATED, symbol, {"side": side.value, "quantity": quantity, "idempotency_key": f"preview:{preview.correlation_id}"}, preview.correlation_id)
        if self.idempotency_store is not None:
            self.idempotency_store.register_idempotency_key(f"preview:{preview.correlation_id}")
        if self.event_bus is not None:
            self.event_bus.publish(event)
        elif self.idempotency_store is not None:
            self.idempotency_store.append(event)
        return preview

    def submit_real_order(self, preview: ZerodhaOrderPreview, *, explicit_test_approval: bool = False, kite_client: object | None = None) -> RealOrderResult:
        if not explicit_test_approval or kite_client is None:
            if self.event_bus is not None:
                self.event_bus.publish(RuntimeEvent(RuntimeEventType.UNSAFE_ACTION_BLOCKED, preview.symbol, {"reason": "real order placement blocked by default"}, preview.correlation_id, severity="CRITICAL"))
                self.event_bus.publish(RuntimeEvent(RuntimeEventType.REAL_ORDER_BLOCKED, preview.symbol, {"reason": "NO_REAL_ORDER_PLACED"}, preview.correlation_id, severity="CRITICAL"))
            return RealOrderResult(RealOrderSafetyStatus.NO_REAL_ORDER_PLACED, preview, reason="real order placement blocked by default")
        order_id = f"test-order-{preview.correlation_id}"
        return RealOrderResult(RealOrderSafetyStatus.TEST_ORDER_PLACED, preview, broker_order_id=order_id)
