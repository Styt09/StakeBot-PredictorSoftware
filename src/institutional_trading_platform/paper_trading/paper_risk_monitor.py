"""Paper runtime risk monitor."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .paper_portfolio import PaperPortfolio


@dataclass
class PaperRiskMonitor:
    portfolio: PaperPortfolio
    initial_capital: float = 100_000.0
    max_daily_loss_percent: float = 1.0
    max_trades_per_day: int = 5
    max_open_positions: int = 2
    max_exposure_percent: float = 100.0
    kill_switch_active: bool = False
    trades_today: int = 0

    def assess(self, *, timestamp: datetime, stale_data: bool = False, prices: dict[str, float] | None = None) -> tuple[bool, tuple[str, ...]]:
        reasons: list[str] = []
        if self.kill_switch_active:
            reasons.append("kill switch active")
        if stale_data:
            reasons.append("stale data block")
        max_loss = self.initial_capital * self.max_daily_loss_percent / 100.0
        daily_loss = -min(0.0, self.portfolio.daily_pnl(timestamp.date()))
        if daily_loss >= max_loss:
            reasons.append("daily loss limit hit")
        if self.trades_today >= self.max_trades_per_day:
            reasons.append("max trades per day hit")
        if len(self.portfolio.open_positions) >= self.max_open_positions:
            reasons.append("max open positions hit")
        exposure_limit = self.initial_capital * self.max_exposure_percent / 100.0
        if self.portfolio.exposure(prices or {}) > exposure_limit:
            reasons.append("max exposure hit")
        return (not reasons, tuple(reasons))

    def record_trade(self) -> None:
        self.trades_today += 1

    def reset_daily(self) -> None:
        self.trades_today = 0
