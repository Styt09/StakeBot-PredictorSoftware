"""Institutional performance metrics for ALPHA-GATE X validation."""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from statistics import mean, pstdev
from typing import Sequence

from ..market_data_spine import TradeRecord


@dataclass(frozen=True)
class PerformanceMetrics:
    """Complete backtest metric set with safe zero-case handling."""

    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    gross_profit: float
    gross_loss: float
    net_profit: float
    profit_factor: float
    expectancy: float
    average_win: float
    average_loss: float
    average_risk_reward: float
    max_drawdown: float
    max_drawdown_percentage: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    largest_win: float
    largest_loss: float
    max_consecutive_wins: int
    max_consecutive_losses: int
    exposure_time: float
    no_trade_percentage: float
    average_holding_period: float
    slippage_cost: float
    brokerage_cost: float


def calculate_performance_metrics(
    trades: Sequence[TradeRecord],
    equity_curve: Sequence[float],
    *,
    initial_capital: float,
    opportunities: int | None = None,
    no_trade_count: int = 0,
    slippage_cost: float = 0.0,
    brokerage_cost: float = 0.0,
) -> PerformanceMetrics:
    """Calculate institutional metrics while handling zero-trade/loss cases."""

    total = len(trades)
    pnls = [trade.pnl for trade in trades]
    wins = [pnl for pnl in pnls if pnl > 0]
    losses = [pnl for pnl in pnls if pnl < 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    net_profit = sum(pnls)
    max_dd, max_dd_pct = max_drawdown(equity_curve)
    holding_periods = [(trade.exit_time - trade.entry_time).total_seconds() for trade in trades]
    average_win = (gross_profit / len(wins)) if wins else 0.0
    average_loss = (sum(losses) / len(losses)) if losses else 0.0
    average_risk_reward = (average_win / abs(average_loss)) if average_win and average_loss else 0.0
    denominator = opportunities if opportunities is not None and opportunities > 0 else max(total + no_trade_count, 1)
    returns = _returns(equity_curve)
    downside = [value for value in returns if value < 0]
    return PerformanceMetrics(
        total_trades=total,
        winning_trades=len(wins),
        losing_trades=len(losses),
        win_rate=(len(wins) / total * 100.0) if total else 0.0,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        net_profit=net_profit,
        profit_factor=(gross_profit / gross_loss) if gross_loss else (float("inf") if gross_profit > 0 else 0.0),
        expectancy=(net_profit / total) if total else 0.0,
        average_win=average_win,
        average_loss=average_loss,
        average_risk_reward=average_risk_reward,
        max_drawdown=max_dd,
        max_drawdown_percentage=max_dd_pct,
        sharpe_ratio=_ratio(returns),
        sortino_ratio=_ratio(returns, downside_only=True),
        calmar_ratio=(net_profit / initial_capital / max_dd_pct) if max_dd_pct > 0 and initial_capital > 0 else 0.0,
        largest_win=max(wins) if wins else 0.0,
        largest_loss=min(losses) if losses else 0.0,
        max_consecutive_wins=_max_streak(pnls, positive=True),
        max_consecutive_losses=_max_streak(pnls, positive=False),
        exposure_time=(sum(holding_periods) / denominator) if denominator else 0.0,
        no_trade_percentage=(no_trade_count / denominator * 100.0) if denominator else 0.0,
        average_holding_period=(mean(holding_periods) if holding_periods else 0.0),
        slippage_cost=slippage_cost,
        brokerage_cost=brokerage_cost,
    )


def max_drawdown(equity_curve: Sequence[float]) -> tuple[float, float]:
    """Return maximum drawdown amount and percentage."""

    if not equity_curve:
        return 0.0, 0.0
    peak = equity_curve[0]
    max_amount = 0.0
    max_pct = 0.0
    for equity in equity_curve:
        peak = max(peak, equity)
        amount = peak - equity
        pct = (amount / peak * 100.0) if peak else 0.0
        max_amount = max(max_amount, amount)
        max_pct = max(max_pct, pct)
    return max_amount, max_pct


def _returns(equity_curve: Sequence[float]) -> list[float]:
    return [(current - previous) / previous for previous, current in zip(equity_curve, equity_curve[1:]) if previous]


def _ratio(returns: Sequence[float], downside_only: bool = False) -> float:
    if not returns:
        return 0.0
    numerator = mean(returns)
    sample = [value for value in returns if value < 0] if downside_only else list(returns)
    if not sample:
        return 0.0
    denominator = pstdev(sample)
    return (numerator / denominator * sqrt(252)) if denominator else 0.0


def _max_streak(pnls: Sequence[float], *, positive: bool) -> int:
    best = current = 0
    for pnl in pnls:
        hit = pnl > 0 if positive else pnl < 0
        current = current + 1 if hit else 0
        best = max(best, current)
    return best
