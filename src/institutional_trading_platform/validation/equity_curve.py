"""Equity curve helpers for ALPHA-GATE X validation."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Sequence

from ..market_data_spine import TradeRecord


def build_equity_curve(initial_capital: float, trades: Sequence[TradeRecord]) -> tuple[float, ...]:
    """Build equity after each trade."""

    equity = initial_capital
    curve = [equity]
    for trade in trades:
        equity += trade.pnl
        curve.append(equity)
    return tuple(curve)


def drawdown_curve(equity_curve: Sequence[float]) -> tuple[float, ...]:
    """Return drawdown amount at each equity point."""

    if not equity_curve:
        return ()
    peak = equity_curve[0]
    values: list[float] = []
    for equity in equity_curve:
        peak = max(peak, equity)
        values.append(peak - equity)
    return tuple(values)


def peak_equity_curve(equity_curve: Sequence[float]) -> tuple[float, ...]:
    """Return running peak equity."""

    peak = float("-inf")
    peaks: list[float] = []
    for equity in equity_curve:
        peak = max(peak, equity)
        peaks.append(peak)
    return tuple(peaks)


def pnl_series(trades: Sequence[TradeRecord]) -> tuple[float, ...]:
    """Return per-trade P&L series."""

    return tuple(trade.pnl for trade in trades)


def daily_pnl(trades: Sequence[TradeRecord]) -> dict[str, float]:
    """Aggregate P&L by exit date."""

    values: defaultdict[date, float] = defaultdict(float)
    for trade in trades:
        values[trade.exit_time.date()] += trade.pnl
    return {key.isoformat(): values[key] for key in sorted(values)}


def monthly_pnl(trades: Sequence[TradeRecord]) -> dict[str, float]:
    """Aggregate P&L by exit month."""

    values: defaultdict[str, float] = defaultdict(float)
    for trade in trades:
        key = f"{trade.exit_time.year:04d}-{trade.exit_time.month:02d}"
        values[key] += trade.pnl
    return dict(sorted(values.items()))
