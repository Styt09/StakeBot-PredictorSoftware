"""Approved trade-plan SL/target monitor that suggests exits only."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ..alpha_gate_x import AlphaSignal
from ..runtime.event_bus import EventBus, RuntimeEvent, RuntimeEventType
from .order_preview import ZerodhaOrderPreview, ZerodhaOrderSafetyWrapper


class ExitReason(StrEnum):
    STOP_LOSS = "STOP_LOSS"
    TARGET = "TARGET"


@dataclass(frozen=True)
class ApprovedTradePlan:
    correlation_id: str
    symbol: str
    exchange: str
    side: AlphaSignal
    quantity: int
    entry_price: float
    stop_loss: float | None
    target: float | None


@dataclass(frozen=True)
class ExitSuggestion:
    plan: ApprovedTradePlan
    reason: ExitReason
    ltp: float
    preview: ZerodhaOrderPreview | None = None


class SLTargetMonitor:
    """Monitor LTP and emit exit suggestions; never auto-exit."""

    def __init__(self, wrapper: ZerodhaOrderSafetyWrapper, event_bus: EventBus | None = None) -> None:
        self.wrapper = wrapper
        self.event_bus = event_bus
        self.plans: dict[str, ApprovedTradePlan] = {}

    def track(self, plan: ApprovedTradePlan) -> None:
        self.plans[plan.correlation_id] = plan

    def on_ltp(self, symbol: str, ltp: float) -> tuple[ExitSuggestion, ...]:
        suggestions: list[ExitSuggestion] = []
        for plan in tuple(self.plans.values()):
            if plan.symbol != symbol:
                continue
            reason: ExitReason | None = None
            if plan.side == AlphaSignal.BUY:
                if plan.stop_loss is not None and ltp <= plan.stop_loss:
                    reason = ExitReason.STOP_LOSS
                elif plan.target is not None and ltp >= plan.target:
                    reason = ExitReason.TARGET
            else:
                if plan.stop_loss is not None and ltp >= plan.stop_loss:
                    reason = ExitReason.STOP_LOSS
                elif plan.target is not None and ltp <= plan.target:
                    reason = ExitReason.TARGET
            if reason is not None:
                exit_side = AlphaSignal.SELL if plan.side == AlphaSignal.BUY else AlphaSignal.BUY
                preview = self.wrapper.preview(correlation_id=plan.correlation_id, symbol=plan.symbol, exchange=plan.exchange, side=exit_side, quantity=plan.quantity, price=ltp)
                suggestion = ExitSuggestion(plan, reason, ltp, preview)
                suggestions.append(suggestion)
                if self.event_bus is not None:
                    self.event_bus.publish(RuntimeEvent(RuntimeEventType.EXIT_SUGGESTED, plan.symbol, {"reason": reason.value, "ltp": ltp}, plan.correlation_id))
        return tuple(suggestions)
