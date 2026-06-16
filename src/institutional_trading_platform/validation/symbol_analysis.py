"""Symbol-level performance analysis for ALPHA-GATE X."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import groupby
from typing import Sequence

from ..market_data_spine import TradeRecord
from .equity_curve import build_equity_curve
from .performance_metrics import calculate_performance_metrics


@dataclass(frozen=True)
class SymbolPerformance:
    symbol: str
    total_trades: int
    win_rate: float
    net_pnl: float
    profit_factor: float
    max_drawdown: float


@dataclass(frozen=True)
class SymbolAnalysis:
    by_symbol: dict[str, SymbolPerformance]
    best_symbol: str | None
    worst_symbol: str | None


def analyze_by_symbol(trades: Sequence[TradeRecord], initial_capital: float = 100_000.0) -> SymbolAnalysis:
    """Aggregate trades by symbol."""

    by_symbol: dict[str, SymbolPerformance] = {}
    for symbol, group in groupby(sorted(trades, key=lambda trade: trade.symbol), key=lambda trade: trade.symbol):
        subset = tuple(group)
        metrics = calculate_performance_metrics(subset, build_equity_curve(initial_capital, subset), initial_capital=initial_capital)
        by_symbol[symbol] = SymbolPerformance(symbol, metrics.total_trades, metrics.win_rate, metrics.net_profit, metrics.profit_factor, metrics.max_drawdown)
    best = max(by_symbol.values(), key=lambda item: item.net_pnl).symbol if by_symbol else None
    worst = min(by_symbol.values(), key=lambda item: item.net_pnl).symbol if by_symbol else None
    return SymbolAnalysis(by_symbol, best, worst)
