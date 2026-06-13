"""Runtime configuration for ALPHA-GATE X live paper trading."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time, timedelta
from zoneinfo import ZoneInfo

from ..alpha_gate_x import TradingMode
from ..alpha_gate_x_indicators import TradingProfile
from ..market_data_spine import CandleTimeframe


@dataclass(frozen=True)
class RuntimeConfig:
    """Safe runtime defaults for Phase 5 paper-only orchestration."""

    trading_mode: TradingMode = TradingMode.PAPER_TRADING
    allowed_symbols: tuple[str, ...] = ("RELIANCE",)
    allowed_timeframes: tuple[CandleTimeframe, ...] = (
        CandleTimeframe.ONE_MINUTE,
        CandleTimeframe.FIVE_MINUTES,
        CandleTimeframe.FIFTEEN_MINUTES,
        CandleTimeframe.ONE_HOUR,
        CandleTimeframe.DAILY,
    )
    trading_profile: TradingProfile = TradingProfile.INTRADAY
    paper_initial_capital: float = 100_000.0
    brokerage_per_order: float = 20.0
    slippage_percent: float = 0.02
    max_runtime_symbols: int = 20
    max_ticks_per_second: int = 1000
    heartbeat_interval: timedelta = timedelta(seconds=30)
    stale_feed_timeout: timedelta = timedelta(seconds=5)
    session_start: time = time(9, 15)
    session_end: time = time(15, 30)
    enable_first_5_min_trading: bool = False
    square_off_time: time = time(15, 15)
    timezone_name: str = "Asia/Kolkata"
    max_daily_loss_percent: float = 1.0
    max_trades_per_day: int = 5
    max_open_positions: int = 2
    max_exposure_percent: float = 100.0
    ready_for_approval_min_trades: int = 100
    ready_for_approval_min_profit_factor: float = 1.5

    def __post_init__(self) -> None:
        if self.trading_mode == TradingMode.LIVE_AUTO:
            raise ValueError("Phase 6 runtime rejects LIVE_AUTO; use PAPER_TRADING only or APPROVAL_REQUIRED")
        if self.trading_mode not in {TradingMode.PAPER_TRADING, TradingMode.APPROVAL_REQUIRED}:
            raise ValueError("runtime mode must be PAPER_TRADING or APPROVAL_REQUIRED")
        if len(self.allowed_symbols) > self.max_runtime_symbols:
            raise ValueError("allowed symbols exceed max_runtime_symbols")
        if self.paper_initial_capital <= 0:
            raise ValueError("paper initial capital must be positive")
        if self.max_ticks_per_second <= 0:
            raise ValueError("max_ticks_per_second must be positive")
        ZoneInfo(self.timezone_name)
