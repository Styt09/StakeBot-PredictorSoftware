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


@dataclass(frozen=True)
class ChildOrder:
    """Scheduled child order for execution algorithms."""

    sequence: int
    quantity: int
    limit_price: float | None = None

    def __post_init__(self) -> None:
        if self.sequence < 0 or self.quantity <= 0:
            raise ValueError("sequence must be non-negative and quantity positive")
        if self.limit_price is not None and self.limit_price <= 0:
            raise ValueError("limit_price must be positive when provided")


def twap_schedule(total_quantity: int, slices: int) -> tuple[ChildOrder, ...]:
    """Create a TWAP child-order schedule."""

    if total_quantity <= 0 or slices <= 0:
        raise ValueError("total_quantity and slices must be positive")
    base = total_quantity // slices
    remainder = total_quantity % slices
    return tuple(ChildOrder(sequence, base + (1 if sequence < remainder else 0)) for sequence in range(slices) if base + (1 if sequence < remainder else 0) > 0)


def vwap_schedule(total_quantity: int, volume_curve: tuple[float, ...]) -> tuple[ChildOrder, ...]:
    """Create a VWAP schedule from an expected volume curve."""

    if total_quantity <= 0 or not volume_curve or any(value < 0 for value in volume_curve):
        raise ValueError("invalid VWAP inputs")
    total_volume = sum(volume_curve)
    if total_volume <= 0:
        raise ValueError("volume curve must have positive mass")
    raw = [int(total_quantity * value / total_volume) for value in volume_curve]
    while sum(raw) < total_quantity:
        raw[raw.index(max(raw))] += 1
    return tuple(ChildOrder(sequence, quantity) for sequence, quantity in enumerate(raw) if quantity > 0)


def iceberg_schedule(total_quantity: int, display_quantity: int) -> tuple[ChildOrder, ...]:
    """Create an iceberg schedule with fixed displayed quantity."""

    if total_quantity <= 0 or display_quantity <= 0:
        raise ValueError("quantities must be positive")
    orders = []
    remaining = total_quantity
    sequence = 0
    while remaining > 0:
        quantity = min(display_quantity, remaining)
        orders.append(ChildOrder(sequence, quantity))
        remaining -= quantity
        sequence += 1
    return tuple(orders)


def participation_schedule(total_quantity: int, market_volumes: tuple[float, ...], participation_rate: float) -> tuple[ChildOrder, ...]:
    """Participation algorithm constrained by market volumes."""

    if total_quantity <= 0 or not 0 < participation_rate <= 1 or not market_volumes:
        raise ValueError("invalid participation inputs")
    child_orders = []
    remaining = total_quantity
    for sequence, market_volume in enumerate(market_volumes):
        if market_volume < 0:
            raise ValueError("market volumes cannot be negative")
        quantity = min(remaining, int(market_volume * participation_rate))
        if quantity > 0:
            child_orders.append(ChildOrder(sequence, quantity))
            remaining -= quantity
        if remaining == 0:
            break
    if remaining > 0:
        child_orders.append(ChildOrder(len(market_volumes), remaining))
    return tuple(child_orders)


def adaptive_execution_style(spread_bps: float, volatility: float, urgency: float) -> str:
    """Select execution style from market conditions and urgency."""

    if spread_bps < 0 or volatility < 0 or not 0 <= urgency <= 1:
        raise ValueError("invalid adaptive execution inputs")
    if urgency > 0.8 or volatility > 0.05:
        return "PARTICIPATION"
    if spread_bps > 25:
        return "ICEBERG"
    return "VWAP"


class OrderManager:
    """In-memory order, position, holdings, and reconciliation manager."""

    def __init__(self) -> None:
        self.orders: dict[str, OrderIntent] = {}
        self.positions: dict[str, int] = {}
        self.holdings: dict[str, int] = {}

    def submit(self, intent: OrderIntent, policy: ExecutionPolicy, last_price: float, average_daily_volume: float, kill_switch: KillSwitchState | None = None) -> tuple[str, ...]:
        """Validate and record an order intent when no policy violations exist."""

        if kill_switch is not None:
            kill_switch.assert_can_trade()
        violations = validate_order_intent(intent, policy, last_price, average_daily_volume)
        if not violations:
            self.orders[intent.client_order_id] = intent
        return violations

    def apply_fill(self, client_order_id: str, quantity: int) -> None:
        """Update positions from a fill quantity."""

        if client_order_id not in self.orders:
            raise ValueError("unknown order")
        if quantity <= 0:
            raise ValueError("fill quantity must be positive")
        order = self.orders[client_order_id]
        signed = quantity if order.side == OrderSide.BUY else -quantity
        key = order.instrument.instrument_id
        self.positions[key] = self.positions.get(key, 0) + signed

    def reconcile_positions(self, broker_positions: dict[str, int]) -> dict[str, int]:
        """Return position differences versus broker state."""

        breaks = {}
        for key in sorted(set(self.positions) | set(broker_positions)):
            difference = broker_positions.get(key, 0) - self.positions.get(key, 0)
            if difference:
                breaks[key] = difference
        return breaks
