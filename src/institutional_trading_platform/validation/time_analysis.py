"""Time-based performance analysis for ALPHA-GATE X."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Sequence

from ..market_data_spine import TradeRecord


@dataclass(frozen=True)
class TimeAnalysis:
    by_hour: dict[int, float]
    by_day_of_week: dict[int, float]
    by_month: dict[str, float]
    first_5_minutes_blocked_impact: int
    last_15_minutes_warning_count: int


def analyze_by_time(trades: Sequence[TradeRecord], first_5_minutes_blocked: int = 0) -> TimeAnalysis:
    """Aggregate P&L by hour, weekday, and month."""

    by_hour: defaultdict[int, float] = defaultdict(float)
    by_day: defaultdict[int, float] = defaultdict(float)
    by_month: defaultdict[str, float] = defaultdict(float)
    last_15 = 0
    for trade in trades:
        by_hour[trade.entry_time.hour] += trade.pnl
        by_day[trade.entry_time.weekday()] += trade.pnl
        by_month[f"{trade.entry_time.year:04d}-{trade.entry_time.month:02d}"] += trade.pnl
        if trade.entry_time.hour == 15 and trade.entry_time.minute >= 15:
            last_15 += 1
    return TimeAnalysis(dict(sorted(by_hour.items())), dict(sorted(by_day.items())), dict(sorted(by_month.items())), first_5_minutes_blocked, last_15)
