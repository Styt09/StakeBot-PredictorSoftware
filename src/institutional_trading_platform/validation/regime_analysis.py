"""Regime performance analysis for ALPHA-GATE X."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from ..market_data_spine import TradeRecord
from .performance_metrics import calculate_performance_metrics


REGIMES = ("BULLISH_TREND", "BEARISH_TREND", "RANGE", "HIGH_VOLATILITY", "DANGER", "UNKNOWN")


@dataclass(frozen=True)
class RegimePerformance:
    trades: int
    win_rate: float
    profit_factor: float
    average_pnl: float
    max_drawdown: float
    no_trade_frequency: int


def analyze_by_regime(trades: Sequence[TradeRecord], trade_regimes: Mapping[int, str], no_trade_regimes: Sequence[str] = ()) -> dict[str, RegimePerformance]:
    """Aggregate performance by market regime."""

    result = {}
    for regime in REGIMES:
        subset = tuple(trade for index, trade in enumerate(trades) if trade_regimes.get(index, "UNKNOWN") == regime)
        metrics = calculate_performance_metrics(subset, _equity(subset), initial_capital=100_000.0, no_trade_count=no_trade_regimes.count(regime))
        result[regime] = RegimePerformance(
            trades=len(subset),
            win_rate=metrics.win_rate,
            profit_factor=metrics.profit_factor,
            average_pnl=metrics.expectancy,
            max_drawdown=metrics.max_drawdown,
            no_trade_frequency=no_trade_regimes.count(regime),
        )
    return result


def _equity(trades: Sequence[TradeRecord]) -> tuple[float, ...]:
    equity = 100_000.0
    curve = [equity]
    for trade in trades:
        equity += trade.pnl
        curve.append(equity)
    return tuple(curve)
