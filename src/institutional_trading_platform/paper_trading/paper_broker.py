"""Deterministic paper broker for virtual ALPHA-GATE X orders."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import uuid4

from ..alpha_gate_x import AlphaSignal, OrderState
from ..market_data_spine import TradeRecord
from ..execution_simulation import ExecutionMode
from .paper_portfolio import PaperPortfolio, PaperPosition, ClosedPaperPosition


class PaperOrderType(StrEnum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


@dataclass(frozen=True)
class PaperOrder:
    correlation_id: str
    symbol: str
    side: AlphaSignal
    quantity: int
    order_type: PaperOrderType = PaperOrderType.MARKET
    requested_price: float | None = None
    stop_loss: float | None = None
    target_1: float | None = None
    target_2: float | None = None
    trailing_stop: float | None = None
    created_at: datetime | None = None


@dataclass(frozen=True)
class PaperFill:
    correlation_id: str
    order_id: str
    symbol: str
    side: AlphaSignal
    quantity: int
    price: float
    brokerage: float
    slippage: float
    timestamp: datetime


@dataclass(frozen=True)
class PaperOrderResult:
    correlation_id: str
    order_id: str
    status: OrderState
    fill: PaperFill | None = None
    rejection_reason: str | None = None


@dataclass
class PaperBroker:
    portfolio: PaperPortfolio
    brokerage_per_order: float = 20.0
    slippage_percent: float = 0.02
    execution_mode: ExecutionMode = ExecutionMode.CONSERVATIVE
    order_book: list[PaperOrderResult] = field(default_factory=list)

    def place_order(self, order: PaperOrder, market_price: float, timestamp: datetime, *, risk_approved: bool = True) -> PaperOrderResult:
        if not risk_approved:
            return self._reject(order, "risk config failed")
        if order.quantity <= 0:
            return self._reject(order, "quantity must be positive")
        if not self.portfolio.can_open_position():
            return self._reject(order, "max open positions hit")
        if order.side not in {AlphaSignal.BUY, AlphaSignal.SELL}:
            return self._reject(order, "paper side must be BUY or SELL")
        if order.order_type == PaperOrderType.LIMIT and order.requested_price is not None:
            if order.side == AlphaSignal.BUY and market_price > order.requested_price:
                return self._open(order, OrderState.ORDER_OPEN)
            if order.side == AlphaSignal.SELL and market_price < order.requested_price:
                return self._open(order, OrderState.ORDER_OPEN)
        fill_price, slippage = self._fill_price(market_price, order.side, entry=True)
        order_id = f"paper-{uuid4()}"
        fill = PaperFill(order.correlation_id, order_id, order.symbol, order.side, order.quantity, fill_price, self.brokerage_per_order, slippage, timestamp)
        result = PaperOrderResult(order.correlation_id, order_id, OrderState.ORDER_FILLED, fill)
        self.order_book.append(result)
        self.portfolio.cash_balance -= self.brokerage_per_order
        self.portfolio.open_position(PaperPosition(order.correlation_id, order.symbol, order.side, order.quantity, fill_price, timestamp, order.stop_loss, order.target_1, order.target_2, order.trailing_stop))
        return result

    def check_exits(self, symbol: str, high: float, low: float, close: float, timestamp: datetime) -> tuple[ClosedPaperPosition, ...]:
        closed: list[ClosedPaperPosition] = []
        for position in tuple(self.portfolio.open_positions.values()):
            if position.symbol != symbol:
                continue
            exit_price: float | None = None
            if position.side == AlphaSignal.BUY:
                if position.stop_loss is not None and low <= position.stop_loss:
                    exit_price = position.stop_loss
                elif position.target_1 is not None and high >= position.target_1:
                    exit_price = position.target_1
            else:
                if position.stop_loss is not None and high >= position.stop_loss:
                    exit_price = position.stop_loss
                elif position.target_1 is not None and low <= position.target_1:
                    exit_price = position.target_1
            if exit_price is not None:
                fill_price, _ = self._fill_price(exit_price, position.side, entry=False)
                closed.append(self.portfolio.close_position(position.correlation_id, fill_price, timestamp, cost=self.brokerage_per_order))
        return tuple(closed)

    def square_off_all(self, prices: dict[str, float], timestamp: datetime) -> tuple[ClosedPaperPosition, ...]:
        closed: list[ClosedPaperPosition] = []
        for position in tuple(self.portfolio.open_positions.values()):
            price = prices.get(position.symbol, position.entry_price)
            fill_price, _ = self._fill_price(price, position.side, entry=False)
            closed.append(self.portfolio.close_position(position.correlation_id, fill_price, timestamp, cost=self.brokerage_per_order))
        return tuple(closed)

    def closed_trades(self) -> tuple[TradeRecord, ...]:
        return tuple(TradeRecord(position.symbol, position.side, position.opened_at, position.closed_at, position.entry_price, position.exit_price, position.quantity, position.pnl) for position in self.portfolio.closed_positions)

    def _reject(self, order: PaperOrder, reason: str) -> PaperOrderResult:
        result = PaperOrderResult(order.correlation_id, f"paper-reject-{uuid4()}", OrderState.ORDER_REJECTED, rejection_reason=reason)
        self.order_book.append(result)
        return result

    def _open(self, order: PaperOrder, status: OrderState) -> PaperOrderResult:
        result = PaperOrderResult(order.correlation_id, f"paper-open-{uuid4()}", status)
        self.order_book.append(result)
        return result

    def _fill_price(self, price: float, side: AlphaSignal, *, entry: bool) -> tuple[float, float]:
        slippage = price * (self.slippage_percent / 100.0)
        adverse = (side == AlphaSignal.BUY and entry) or (side == AlphaSignal.SELL and not entry)
        return (price + slippage if adverse else price - slippage), slippage
