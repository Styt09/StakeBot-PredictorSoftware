"""Approval-required trading workflow for Phase 6."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import uuid4

from ..alpha_gate_x import AlphaSignal, TradingMode
from ..alpha_gate_x_indicators import IndicatorSignalOutput
from ..runtime.event_bus import EventBus, RuntimeEvent, RuntimeEventType
from ..runtime.runtime_config import RuntimeConfig
from .order_preview import ZerodhaOrderPreview, ZerodhaOrderSafetyWrapper
from .reconciliation import BrokerReconciliationService


class ApprovalStatus(StrEnum):
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class TradeApprovalRequest:
    request_id: str
    correlation_id: str
    symbol: str
    side: AlphaSignal
    quantity: int
    entry_reference: float | None
    stop_loss: float | None
    target_1: float | None
    status: ApprovalStatus
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class TradeApprovalDecision:
    request: TradeApprovalRequest
    approved: bool
    preview: ZerodhaOrderPreview | None = None
    reasons: tuple[str, ...] = ()


class ApprovalModeService:
    """Create approval requests and previews, never automatic real orders."""

    def __init__(self, config: RuntimeConfig, reconciliation: BrokerReconciliationService, wrapper: ZerodhaOrderSafetyWrapper, event_bus: EventBus | None = None) -> None:
        if config.trading_mode == TradingMode.LIVE_AUTO:
            raise ValueError("LIVE_AUTO is rejected in Phase 6 approval workflow")
        self.config = config
        self.reconciliation = reconciliation
        self.wrapper = wrapper
        self.event_bus = event_bus

    def request_approval(self, signal: IndicatorSignalOutput, quantity: int = 1) -> TradeApprovalRequest:
        if not self.reconciliation.last_result.passed:
            request = TradeApprovalRequest(f"approval-{uuid4()}", signal.correlation_id, signal.symbol, signal.signal, 0, signal.entry_reference, signal.stop_loss, signal.target_1, ApprovalStatus.BLOCKED, self.reconciliation.last_result.reasons)
            self._emit(RuntimeEventType.TRADE_REJECTED, signal.symbol, {"reasons": request.reasons}, signal.correlation_id)
            return request
        if signal.signal not in {AlphaSignal.BUY, AlphaSignal.SELL}:
            request = TradeApprovalRequest(f"approval-{uuid4()}", signal.correlation_id, signal.symbol, signal.signal, 0, signal.entry_reference, signal.stop_loss, signal.target_1, ApprovalStatus.REJECTED, ("signal is not actionable",))
            self._emit(RuntimeEventType.TRADE_REJECTED, signal.symbol, {"reasons": request.reasons}, signal.correlation_id)
            return request
        request = TradeApprovalRequest(f"approval-{uuid4()}", signal.correlation_id, signal.symbol, signal.signal, quantity, signal.entry_reference, signal.stop_loss, signal.target_1, ApprovalStatus.APPROVAL_REQUIRED)
        self._emit(RuntimeEventType.TRADE_APPROVAL_REQUESTED, signal.symbol, {"request_id": request.request_id, "side": signal.signal.value}, signal.correlation_id)
        return request

    def approve(self, request: TradeApprovalRequest, *, user_approved: bool) -> TradeApprovalDecision:
        if not user_approved:
            rejected = TradeApprovalRequest(**{**request.__dict__, "status": ApprovalStatus.REJECTED, "reasons": ("user rejected",)})
            self._emit(RuntimeEventType.TRADE_REJECTED, request.symbol, {"reasons": rejected.reasons}, request.correlation_id)
            return TradeApprovalDecision(rejected, False, reasons=rejected.reasons)
        preview = self.wrapper.preview(correlation_id=request.correlation_id, symbol=request.symbol, exchange="NSE", side=request.side, quantity=request.quantity, price=request.entry_reference, stop_loss=request.stop_loss, target=request.target_1)
        approved = TradeApprovalRequest(**{**request.__dict__, "status": ApprovalStatus.APPROVED})
        self._emit(RuntimeEventType.TRADE_APPROVED, request.symbol, {"request_id": request.request_id}, request.correlation_id)
        return TradeApprovalDecision(approved, True, preview=preview)

    def _emit(self, event_type: RuntimeEventType, symbol: str, payload: dict[str, object], correlation_id: str) -> None:
        if self.event_bus is not None:
            self.event_bus.publish(RuntimeEvent(event_type, symbol, payload, correlation_id))
