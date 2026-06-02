"""Execution controls, broker-neutral order models, and kill-switch logic."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from math import isfinite
from uuid import uuid4

from .domain import Instrument
from .signal_engine import MarketDecision, SignalOutput


class OrderSide(StrEnum):
    """Broker-neutral order side."""

    BUY = "BUY"
    SELL = "SELL"


class OrderType(StrEnum):
    """Broker-neutral order type."""

    MARKET = "MARKET"
    LIMIT = "LIMIT"


@dataclass(frozen=True)
class ExecutionPolicy:
    """Pre-trade execution and exposure constraints."""

    max_notional: float
    max_quantity: int
    max_participation_rate: float
    allowed_slippage_bps: float

    def __post_init__(self) -> None:
        if not isfinite(self.max_notional) or self.max_notional <= 0:
            raise ValueError("max_notional must be positive and finite")
        if self.max_quantity <= 0:
            raise ValueError("max_quantity must be positive")
        if not 0 < self.max_participation_rate <= 1:
            raise ValueError("max_participation_rate must be in (0, 1]")
        if not isfinite(self.allowed_slippage_bps) or self.allowed_slippage_bps < 0:
            raise ValueError("allowed_slippage_bps must be non-negative and finite")


@dataclass(frozen=True)
class OrderIntent:
    """Validated order intent ready for broker adapter translation."""

    instrument: Instrument
    side: OrderSide
    quantity: int
    order_type: OrderType
    limit_price: float | None = None
    client_order_id: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")
        if self.order_type == OrderType.LIMIT:
            if self.limit_price is None or not isfinite(self.limit_price) or self.limit_price <= 0:
                raise ValueError("limit orders require a positive finite limit_price")
        if self.order_type == OrderType.MARKET and self.limit_price is not None:
            raise ValueError("market orders cannot include limit_price")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        if self.client_order_id and not self.client_order_id.strip():
            raise ValueError("client_order_id cannot be blank")


@dataclass(frozen=True)
class KillSwitchState:
    """Global execution halt state."""

    enabled: bool = False
    reason: str = ""
    activated_at: datetime | None = None

    def assert_can_trade(self) -> None:
        """Raise when execution must be halted."""

        if self.enabled:
            reason = self.reason or "kill switch is active"
            raise RuntimeError(reason)


def validate_order_intent(intent: OrderIntent, policy: ExecutionPolicy, last_price: float, average_daily_volume: float) -> tuple[str, ...]:
    """Return all execution policy violations for an order intent."""

    if not isfinite(last_price) or last_price <= 0:
        raise ValueError("last_price must be positive and finite")
    if not isfinite(average_daily_volume) or average_daily_volume < 0:
        raise ValueError("average_daily_volume must be non-negative and finite")
    violations: list[str] = []
    notional = intent.quantity * last_price
    if notional > policy.max_notional:
        violations.append("order notional exceeds policy max_notional")
    if intent.quantity > policy.max_quantity:
        violations.append("order quantity exceeds policy max_quantity")
    if average_daily_volume == 0 or intent.quantity / average_daily_volume > policy.max_participation_rate:
        violations.append("order exceeds participation-rate constraint")
    if intent.limit_price is not None:
        slippage_bps = abs(intent.limit_price - last_price) / last_price * 10_000
        if slippage_bps > policy.allowed_slippage_bps:
            violations.append("limit price exceeds allowed slippage")
    return tuple(violations)


def order_from_signal(instrument: Instrument, signal: SignalOutput, quantity: int | None = None) -> OrderIntent:
    """Convert an approved final signal into a broker-neutral limit order."""

    if not signal.is_tradeable:
        raise ValueError("signal is not tradeable")
    if signal.entry is None:
        raise ValueError("tradeable signals must include entry")
    side = OrderSide.BUY if signal.decision == MarketDecision.BUY else OrderSide.SELL
    order_quantity = quantity if quantity is not None else int(signal.position_size)
    return OrderIntent(
        instrument=instrument,
        side=side,
        quantity=order_quantity,
        order_type=OrderType.LIMIT,
        limit_price=signal.entry,
        client_order_id=f"SB-{uuid4().hex}",
    )
