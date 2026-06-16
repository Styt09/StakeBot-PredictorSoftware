"""Paper portfolio accounting for ALPHA-GATE X Phase 5."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from ..alpha_gate_x import AlphaSignal


@dataclass(frozen=True)
class PaperPosition:
    correlation_id: str
    symbol: str
    side: AlphaSignal
    quantity: int
    entry_price: float
    opened_at: datetime
    stop_loss: float | None = None
    target_1: float | None = None
    target_2: float | None = None
    trailing_stop: float | None = None


@dataclass(frozen=True)
class ClosedPaperPosition:
    correlation_id: str
    symbol: str
    side: AlphaSignal
    quantity: int
    entry_price: float
    exit_price: float
    opened_at: datetime
    closed_at: datetime
    pnl: float


@dataclass
class PaperPortfolio:
    initial_capital: float = 100_000.0
    cash_balance: float = 100_000.0
    max_open_positions: int = 2
    open_positions: dict[str, PaperPosition] = field(default_factory=dict)
    closed_positions: list[ClosedPaperPosition] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.cash_balance == 100_000.0 and self.initial_capital != 100_000.0:
            self.cash_balance = self.initial_capital

    @property
    def realized_pnl(self) -> float:
        return sum(position.pnl for position in self.closed_positions)

    def can_open_position(self) -> bool:
        return len(self.open_positions) < self.max_open_positions

    def open_position(self, position: PaperPosition) -> None:
        if not self.can_open_position():
            raise ValueError("max open positions hit")
        if position.correlation_id in self.open_positions:
            raise ValueError("duplicate paper position")
        self.open_positions[position.correlation_id] = position

    def close_position(self, correlation_id: str, exit_price: float, closed_at: datetime, cost: float = 0.0) -> ClosedPaperPosition:
        position = self.open_positions.pop(correlation_id)
        gross = (exit_price - position.entry_price) * position.quantity if position.side == AlphaSignal.BUY else (position.entry_price - exit_price) * position.quantity
        closed = ClosedPaperPosition(position.correlation_id, position.symbol, position.side, position.quantity, position.entry_price, exit_price, position.opened_at, closed_at, gross - cost)
        self.closed_positions.append(closed)
        self.cash_balance += closed.pnl
        return closed

    def unrealized_pnl(self, prices: dict[str, float]) -> float:
        pnl = 0.0
        for position in self.open_positions.values():
            mark = prices.get(position.symbol, position.entry_price)
            pnl += (mark - position.entry_price) * position.quantity if position.side == AlphaSignal.BUY else (position.entry_price - mark) * position.quantity
        return pnl

    def total_equity(self, prices: dict[str, float] | None = None) -> float:
        return self.cash_balance + self.unrealized_pnl(prices or {})

    def exposure(self, prices: dict[str, float] | None = None) -> float:
        prices = prices or {}
        return sum(abs(prices.get(position.symbol, position.entry_price) * position.quantity) for position in self.open_positions.values())

    def daily_pnl(self, day: date) -> float:
        return sum(position.pnl for position in self.closed_positions if position.closed_at.date() == day)

    def per_symbol_pnl(self) -> dict[str, float]:
        values: dict[str, float] = {}
        for position in self.closed_positions:
            values[position.symbol] = values.get(position.symbol, 0.0) + position.pnl
        return values
