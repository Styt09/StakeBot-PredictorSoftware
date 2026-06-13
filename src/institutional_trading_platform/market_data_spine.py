"""ALPHA-GATE X market data spine, candle builder, and backtest foundation.

The spine is deliberately deterministic and data-provider neutral.  It never
creates synthetic candles for unavailable providers, marks forming candles as
incomplete, and exposes quality failures as explicit risk/data block reasons.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
from enum import StrEnum
from math import isfinite
from typing import Callable, Iterable

from .alpha_gate_x import (
    AlphaGateXEngine,
    AlphaSignal,
    FactorScores,
    MarketRegime,
    RiskContext,
    RiskDecision,
    RiskGate,
    RiskStatus,
)


class DataQualityStatus(StrEnum):
    """Data quality states used to block unsafe signal generation."""

    OK = "OK"
    WARNING = "WARNING"
    FAIL = "FAIL"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"


class CandleTimeframe(StrEnum):
    """Supported ALPHA-GATE X candle timeframes."""

    ONE_MINUTE = "1m"
    FIVE_MINUTES = "5m"
    FIFTEEN_MINUTES = "15m"
    ONE_HOUR = "1H"
    DAILY = "Daily"

    @property
    def duration(self) -> timedelta:
        """Return the timeframe duration."""

        return {
            CandleTimeframe.ONE_MINUTE: timedelta(minutes=1),
            CandleTimeframe.FIVE_MINUTES: timedelta(minutes=5),
            CandleTimeframe.FIFTEEN_MINUTES: timedelta(minutes=15),
            CandleTimeframe.ONE_HOUR: timedelta(hours=1),
            CandleTimeframe.DAILY: timedelta(days=1),
        }[self]


@dataclass(frozen=True)
class Instrument:
    """Tradable instrument identity for market data and broker mapping."""

    symbol: str
    exchange: str = "NSE"
    instrument_token: int | None = None
    tradingsymbol: str | None = None
    segment: str = "NSE"


@dataclass(frozen=True)
class MarketDepth:
    """Top-of-book market depth snapshot."""

    bid_price: float
    bid_quantity: int
    ask_price: float
    ask_quantity: int

    @property
    def spread_percent(self) -> float:
        """Return spread as percentage of mid price."""

        mid = (self.bid_price + self.ask_price) / 2
        if mid <= 0:
            return float("inf")
        return ((self.ask_price - self.bid_price) / mid) * 100


@dataclass(frozen=True)
class Tick:
    """Single market data tick.

    ``quantity`` is the traded quantity represented by this tick.  It is used to
    build candle volume and should be deterministic in tests.
    """

    symbol: str
    exchange: str
    timestamp: datetime
    price: float
    quantity: int = 0
    tick_id: str | None = None
    depth: MarketDepth | None = None

    def validate(self) -> None:
        """Validate tick fields before ingestion."""

        if not self.symbol or not self.exchange:
            raise ValueError("symbol and exchange are required")
        if self.timestamp.tzinfo is None:
            raise ValueError("tick timestamp must be timezone-aware")
        if self.price <= 0 or not isfinite(self.price):
            raise ValueError("tick price must be positive and finite")
        if self.quantity < 0:
            raise ValueError("tick quantity cannot be negative")


@dataclass(frozen=True)
class Quote:
    """Quote payload with optional market depth."""

    symbol: str
    exchange: str
    timestamp: datetime
    last_price: float
    depth: MarketDepth | None = None


@dataclass(frozen=True)
class OHLCVCandle:
    """OHLCV candle with an explicit completion marker."""

    symbol: str
    exchange: str
    timeframe: CandleTimeframe
    start: datetime
    end: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    complete: bool

    def validate(self) -> None:
        """Validate OHLCV invariants and finalized timestamp boundaries."""

        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("candle timestamps must be timezone-aware")
        if self.end <= self.start:
            raise ValueError("candle end must be after start")
        if any(price <= 0 or not isfinite(price) for price in (self.open, self.high, self.low, self.close)):
            raise ValueError("OHLC prices must be positive and finite")
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close) or self.low > self.high:
            raise ValueError("invalid OHLC relationship")
        if self.volume < 0:
            raise ValueError("candle volume cannot be negative")


@dataclass(frozen=True)
class DataQualityReport:
    """Result of market-data quality checks."""

    status: DataQualityStatus
    reasons: tuple[str, ...] = ()

    @property
    def risk_block_reason(self) -> str | None:
        """Return a compact risk/data block reason for the risk gate."""

        if self.status in {DataQualityStatus.FAIL, DataQualityStatus.DATA_UNAVAILABLE}:
            return "; ".join(self.reasons) or self.status.value
        return None


def risk_decision_from_data_quality(report: DataQualityReport) -> RiskDecision | None:
    """Convert a failed data-quality report into a signal-engine risk block."""

    if report.status not in {DataQualityStatus.FAIL, DataQualityStatus.DATA_UNAVAILABLE}:
        return None
    reasons = report.reasons or (report.status.value,)
    return RiskDecision(status=RiskStatus.FAIL, quantity=0, risk_amount=0.0, reasons=reasons)


class CandleBuilder:
    """Convert live ticks into completed and forming OHLCV candles."""

    def __init__(self, timeframes: Iterable[CandleTimeframe] | None = None) -> None:
        self.timeframes = tuple(timeframes or tuple(CandleTimeframe))
        self._current: dict[tuple[str, str, CandleTimeframe], OHLCVCandle] = {}
        self._completed: dict[tuple[str, str, CandleTimeframe], list[OHLCVCandle]] = {}

    def update_tick(self, tick: Tick) -> tuple[OHLCVCandle, ...]:
        """Ingest a tick and return candles finalized by this tick.

        A candle is finalized only when a later tick arrives at or beyond the
        candle end.  The new/current candle remains ``complete=False``.
        """

        tick.validate()
        finalized: list[OHLCVCandle] = []
        for timeframe in self.timeframes:
            key = (tick.symbol, tick.exchange, timeframe)
            bucket_start = floor_timestamp(tick.timestamp, timeframe)
            bucket_end = bucket_start + timeframe.duration
            current = self._current.get(key)
            if current is None:
                self._current[key] = _new_candle(tick, timeframe, bucket_start, bucket_end, complete=False)
                continue
            if tick.timestamp >= current.end:
                completed = _replace_complete(current, True)
                completed.validate()
                self._completed.setdefault(key, []).append(completed)
                finalized.append(completed)
                self._current[key] = _new_candle(tick, timeframe, bucket_start, bucket_end, complete=False)
            else:
                self._current[key] = _update_candle(current, tick)
        return tuple(finalized)

    def current_candle(self, symbol: str, exchange: str, timeframe: CandleTimeframe) -> OHLCVCandle | None:
        """Return the current forming candle, if available."""

        return self._current.get((symbol, exchange, timeframe))

    def completed_candles(self, symbol: str, exchange: str, timeframe: CandleTimeframe) -> tuple[OHLCVCandle, ...]:
        """Return finalized candles only."""

        return tuple(self._completed.get((symbol, exchange, timeframe), ()))


def floor_timestamp(timestamp: datetime, timeframe: CandleTimeframe) -> datetime:
    """Floor a timestamp to the start of its timeframe bucket."""

    if timestamp.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    if timeframe == CandleTimeframe.DAILY:
        return datetime.combine(timestamp.date(), time.min, tzinfo=timestamp.tzinfo)
    day_start = datetime.combine(timestamp.date(), time.min, tzinfo=timestamp.tzinfo)
    elapsed = int((timestamp - day_start).total_seconds())
    duration = int(timeframe.duration.total_seconds())
    return day_start + timedelta(seconds=(elapsed // duration) * duration)


def completed_candles_for_signal(candles: Iterable[OHLCVCandle], allow_incomplete: bool = False) -> tuple[OHLCVCandle, ...]:
    """Return candles eligible for signal generation."""

    return tuple(candle for candle in candles if allow_incomplete or candle.complete)


def _new_candle(tick: Tick, timeframe: CandleTimeframe, start: datetime, end: datetime, complete: bool) -> OHLCVCandle:
    return OHLCVCandle(tick.symbol, tick.exchange, timeframe, start, end, tick.price, tick.price, tick.price, tick.price, tick.quantity, complete)


def _update_candle(candle: OHLCVCandle, tick: Tick) -> OHLCVCandle:
    return OHLCVCandle(
        candle.symbol,
        candle.exchange,
        candle.timeframe,
        candle.start,
        candle.end,
        candle.open,
        max(candle.high, tick.price),
        min(candle.low, tick.price),
        tick.price,
        candle.volume + tick.quantity,
        False,
    )


def _replace_complete(candle: OHLCVCandle, complete: bool) -> OHLCVCandle:
    return OHLCVCandle(
        candle.symbol,
        candle.exchange,
        candle.timeframe,
        candle.start,
        candle.end,
        candle.open,
        candle.high,
        candle.low,
        candle.close,
        candle.volume,
        complete,
    )


@dataclass(frozen=True)
class HistoricalDataResult:
    """Historical candle loader result."""

    status: DataQualityStatus
    candles: tuple[OHLCVCandle, ...] = ()
    errors: tuple[str, ...] = ()


class HistoricalDataLoader(ABC):
    """Abstract historical data provider interface."""

    @abstractmethod
    def load_candles(self, symbol: str, timeframe: CandleTimeframe, start: datetime, end: datetime) -> HistoricalDataResult:
        """Load validated OHLCV candles for the requested range."""


class UnavailableHistoricalDataLoader(HistoricalDataLoader):
    """Provider used when no real historical data integration is configured."""

    def load_candles(self, symbol: str, timeframe: CandleTimeframe, start: datetime, end: datetime) -> HistoricalDataResult:
        return HistoricalDataResult(DataQualityStatus.DATA_UNAVAILABLE, errors=("historical data provider unavailable",))


class DataQualityChecker:
    """Stateful live-market-data and candle quality checks."""

    def __init__(self, stale_after: timedelta = timedelta(seconds=5), max_spread_percent: float = 0.15, max_price_jump_percent: float = 10.0) -> None:
        self.stale_after = stale_after
        self.max_spread_percent = max_spread_percent
        self.max_price_jump_percent = max_price_jump_percent
        self._last_tick: dict[tuple[str, str], Tick] = {}
        self._seen_tick_ids: set[str] = set()

    def check_tick(self, tick: Tick, received_at: datetime | None = None) -> DataQualityReport:
        """Check stale, disordered, duplicate, spread, and outlier tick data."""

        reasons: list[str] = []
        try:
            tick.validate()
        except ValueError as exc:
            return DataQualityReport(DataQualityStatus.FAIL, (str(exc),))
        now = received_at or datetime.now(timezone.utc)
        if now.tzinfo is None:
            raise ValueError("received_at must be timezone-aware")
        if now - tick.timestamp > self.stale_after:
            reasons.append("stale data")
        if tick.tick_id is not None and tick.tick_id in self._seen_tick_ids:
            reasons.append("duplicate tick")
        key = (tick.symbol, tick.exchange)
        previous = self._last_tick.get(key)
        if previous is not None:
            if tick.timestamp < previous.timestamp:
                reasons.append("timestamp disorder")
            if tick.tick_id is None and tick.timestamp == previous.timestamp and tick.price == previous.price and tick.quantity == previous.quantity:
                reasons.append("duplicate tick")
            jump_percent = abs(tick.price - previous.price) / previous.price * 100
            if jump_percent > self.max_price_jump_percent:
                reasons.append("outlier price jump")
        if tick.depth is not None and tick.depth.spread_percent > self.max_spread_percent:
            reasons.append("abnormal spread")
        if tick.tick_id is not None:
            self._seen_tick_ids.add(tick.tick_id)
        self._last_tick[key] = tick
        return DataQualityReport(DataQualityStatus.FAIL if reasons else DataQualityStatus.OK, tuple(reasons))

    def check_candle(self, candle: OHLCVCandle) -> DataQualityReport:
        """Validate OHLCV quality for a candle."""

        reasons: list[str] = []
        try:
            candle.validate()
        except ValueError as exc:
            reasons.append(str(exc))
        if candle.volume == 0:
            reasons.append("zero volume")
        return DataQualityReport(DataQualityStatus.FAIL if reasons else DataQualityStatus.OK, tuple(reasons))


@dataclass(frozen=True)
class BacktestConfig:
    """Costs and starting equity for the backtest foundation."""

    starting_equity: float = 100_000.0
    brokerage_per_trade: float = 20.0
    slippage_percent: float = 0.02


@dataclass(frozen=True)
class TradeRecord:
    """Backtest trade record."""

    symbol: str
    side: AlphaSignal
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    quantity: int
    pnl: float


@dataclass(frozen=True)
class BacktestMetrics:
    """Minimum ALPHA-GATE X backtest metrics."""

    total_trades: int
    win_rate: float
    profit_factor: float
    max_drawdown: float
    average_win: float
    average_loss: float
    expectancy: float
    no_trade_percentage: float




@dataclass(frozen=True)
class SignalRecord:
    """Backtest signal audit record."""

    symbol: str
    timestamp: datetime
    signal: AlphaSignal
    reason: str = ""


@dataclass(frozen=True)
class RiskBlockRecord:
    """Backtest risk-block audit record."""

    symbol: str
    timestamp: datetime
    reason: str


@dataclass(frozen=True)
class DataQualityEventRecord:
    """Backtest data-quality audit record."""

    symbol: str
    timestamp: datetime
    status: DataQualityStatus
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class MultiSymbolBacktestResult:
    """Multi-symbol backtest output with audit records."""

    result: BacktestResult
    signal_records: tuple[SignalRecord, ...]
    risk_block_records: tuple[RiskBlockRecord, ...]
    data_quality_events: tuple[DataQualityEventRecord, ...]


@dataclass(frozen=True)
class BacktestResult:
    """Backtest output with trades, equity curve, and metrics."""

    trades: tuple[TradeRecord, ...]
    equity_curve: tuple[float, ...]
    metrics: BacktestMetrics
    quality: DataQualityReport = field(default_factory=lambda: DataQualityReport(DataQualityStatus.OK))


FactorProvider = Callable[[tuple[OHLCVCandle, ...]], FactorScores | None]


class BacktestEngine:
    """Minimal no-look-ahead backtest runner for ALPHA-GATE X."""

    def __init__(self, signal_engine: AlphaGateXEngine | None = None, risk_gate: RiskGate | None = None, config: BacktestConfig | None = None) -> None:
        self.signal_engine = signal_engine or AlphaGateXEngine()
        self.risk_gate = risk_gate or RiskGate()
        self.config = config or BacktestConfig()

    def run(self, candles: Iterable[OHLCVCandle], factor_provider: FactorProvider) -> BacktestResult:
        """Run candle-by-candle, executing entries on the next candle open."""

        ordered = tuple(candles)
        quality = self._validate_candles(ordered)
        if quality.status == DataQualityStatus.FAIL:
            return BacktestResult((), (self.config.starting_equity,), self._metrics((), (self.config.starting_equity,), len(ordered), len(ordered)), quality)
        equity = self.config.starting_equity
        equity_curve: list[float] = [equity]
        trades: list[TradeRecord] = []
        no_trade_count = 0
        signal_count = 0
        for index in range(0, max(0, len(ordered) - 1)):
            history = ordered[: index + 1]
            factors = factor_provider(history)
            if factors is None:
                no_trade_count += 1
                continue
            signal_count += 1
            current = ordered[index]
            next_candle = ordered[index + 1]
            risk = self.risk_gate.assess(current.close, current.low if current.low != current.close else current.close * 0.99, RiskContext(average_volume=max(current.volume, 1), spread_percent=0.0))
            signal = self.signal_engine.evaluate(
                symbol=current.symbol,
                exchange=current.exchange,
                timeframe=current.timeframe.value,
                factors=factors,
                risk_decision=risk,
                market_regime=MarketRegime.NEUTRAL,
                entry=current.close,
                stop_loss=current.low if current.low != current.close else current.close * 0.99,
                target_1=None,
                target_2=None,
            )
            if signal.signal not in {AlphaSignal.BUY, AlphaSignal.SELL} or risk.status != RiskStatus.PASS:
                no_trade_count += 1
                continue
            entry_price = self._apply_slippage(next_candle.open, signal.signal, entry=True)
            exit_price = self._apply_slippage(next_candle.close, signal.signal, entry=False)
            quantity = max(1, risk.quantity)
            gross = (exit_price - entry_price) * quantity if signal.signal == AlphaSignal.BUY else (entry_price - exit_price) * quantity
            pnl = gross - (2 * self.config.brokerage_per_trade)
            equity += pnl
            equity_curve.append(equity)
            trades.append(TradeRecord(current.symbol, signal.signal, next_candle.start, next_candle.end, entry_price, exit_price, quantity, pnl))
        opportunities = max(signal_count + no_trade_count, len(ordered) - 1, 1)
        return BacktestResult(tuple(trades), tuple(equity_curve), self._metrics(tuple(trades), tuple(equity_curve), no_trade_count, opportunities), quality)


    def run_with_indicator_scoring(self, candles: Iterable[OHLCVCandle], indicator_scorer: Callable[[tuple[OHLCVCandle, ...]], object]) -> BacktestResult:
        """Run a Phase 3 indicator signal scorer without future candle access.

        The scorer receives only completed history through the current candle and
        must return an object with ALPHA-GATE X signal fields such as ``signal``,
        ``stop_loss`` and targets.  Entries still execute on the next candle open
        with configured brokerage and slippage.
        """

        ordered = tuple(candle for candle in candles if candle.complete)
        quality = self._validate_candles(ordered)
        if quality.status == DataQualityStatus.FAIL:
            return BacktestResult((), (self.config.starting_equity,), self._metrics((), (self.config.starting_equity,), len(ordered), len(ordered)), quality)
        equity = self.config.starting_equity
        equity_curve: list[float] = [equity]
        trades: list[TradeRecord] = []
        no_trade_count = 0
        for index in range(0, max(0, len(ordered) - 1)):
            history = ordered[: index + 1]
            signal = indicator_scorer(history)
            decision = getattr(signal, "signal", None)
            if decision not in {AlphaSignal.BUY, AlphaSignal.SELL}:
                no_trade_count += 1
                continue
            next_candle = ordered[index + 1]
            entry_price = self._apply_slippage(next_candle.open, decision, entry=True)
            stop_loss = getattr(signal, "stop_loss", None)
            target_1 = getattr(signal, "target_1", None)
            exit_price = next_candle.close
            if decision == AlphaSignal.BUY:
                if stop_loss is not None and next_candle.low <= stop_loss:
                    exit_price = stop_loss
                elif target_1 is not None and next_candle.high >= target_1:
                    exit_price = target_1
            else:
                if stop_loss is not None and next_candle.high >= stop_loss:
                    exit_price = stop_loss
                elif target_1 is not None and next_candle.low <= target_1:
                    exit_price = target_1
            exit_price = self._apply_slippage(exit_price, decision, entry=False)
            quantity = 1
            gross = (exit_price - entry_price) * quantity if decision == AlphaSignal.BUY else (entry_price - exit_price) * quantity
            pnl = gross - (2 * self.config.brokerage_per_trade)
            equity += pnl
            equity_curve.append(equity)
            trades.append(TradeRecord(next_candle.symbol, decision, next_candle.start, next_candle.end, entry_price, exit_price, quantity, pnl))
        opportunities = max(len(ordered) - 1, 1)
        return BacktestResult(tuple(trades), tuple(equity_curve), self._metrics(tuple(trades), tuple(equity_curve), no_trade_count, opportunities), quality)


    def run_multi_symbol_with_indicator_scoring(self, candles_by_symbol: dict[str, Iterable[OHLCVCandle]], indicator_scorer: Callable[[str, tuple[OHLCVCandle, ...]], object]) -> MultiSymbolBacktestResult:
        """Run Phase 4 multi-symbol validation with signal/risk/data audit records."""

        all_trades: list[TradeRecord] = []
        signal_records: list[SignalRecord] = []
        risk_blocks: list[RiskBlockRecord] = []
        data_events: list[DataQualityEventRecord] = []
        for symbol, candles in candles_by_symbol.items():
            ordered = tuple(candle for candle in candles if candle.complete)
            quality = self._validate_candles(ordered)
            if quality.status == DataQualityStatus.FAIL:
                when = ordered[0].start if ordered else datetime.now(timezone.utc)
                data_events.append(DataQualityEventRecord(symbol, when, quality.status, quality.reasons))
                continue
            for index in range(0, max(0, len(ordered) - 1)):
                history = ordered[: index + 1]
                signal = indicator_scorer(symbol, history)
                decision = getattr(signal, "signal", AlphaSignal.NO_TRADE)
                signal_records.append(SignalRecord(symbol, ordered[index].end, decision, "phase4 multi-symbol audit"))
                if decision not in {AlphaSignal.BUY, AlphaSignal.SELL}:
                    risk_blocks.append(RiskBlockRecord(symbol, ordered[index].end, "signal rejected or no-trade"))
                    continue
                next_candle = ordered[index + 1]
                entry_price = self._apply_slippage(next_candle.open, decision, entry=True)
                exit_price = self._apply_slippage(next_candle.close, decision, entry=False)
                pnl = (exit_price - entry_price) if decision == AlphaSignal.BUY else (entry_price - exit_price)
                pnl -= 2 * self.config.brokerage_per_trade
                all_trades.append(TradeRecord(symbol, decision, next_candle.start, next_candle.end, entry_price, exit_price, 1, pnl))
        equity = [self.config.starting_equity]
        for trade in all_trades:
            equity.append(equity[-1] + trade.pnl)
        result = BacktestResult(tuple(all_trades), tuple(equity), self._metrics(tuple(all_trades), tuple(equity), len(risk_blocks), max(len(signal_records), 1)))
        return MultiSymbolBacktestResult(result, tuple(signal_records), tuple(risk_blocks), tuple(data_events))

    def _apply_slippage(self, price: float, side: AlphaSignal, entry: bool) -> float:
        adjustment = price * (self.config.slippage_percent / 100.0)
        if (side == AlphaSignal.BUY and entry) or (side == AlphaSignal.SELL and not entry):
            return price + adjustment
        return price - adjustment

    @staticmethod
    def _validate_candles(candles: tuple[OHLCVCandle, ...]) -> DataQualityReport:
        checker = DataQualityChecker()
        reasons: list[str] = []
        previous_end: datetime | None = None
        for candle in candles:
            report = checker.check_candle(candle)
            reasons.extend(report.reasons)
            if previous_end is not None:
                if candle.start < previous_end:
                    reasons.append("timestamp disorder")
                elif candle.start > previous_end:
                    reasons.append("missing candle")
            previous_end = candle.end
        return DataQualityReport(DataQualityStatus.FAIL if reasons else DataQualityStatus.OK, tuple(reasons))

    @staticmethod
    def _metrics(trades: tuple[TradeRecord, ...], equity_curve: tuple[float, ...], no_trade_count: int, opportunities: int) -> BacktestMetrics:
        wins = [trade.pnl for trade in trades if trade.pnl > 0]
        losses = [trade.pnl for trade in trades if trade.pnl < 0]
        total_profit = sum(wins)
        total_loss = abs(sum(losses))
        peak = equity_curve[0] if equity_curve else 0.0
        max_drawdown = 0.0
        for value in equity_curve:
            peak = max(peak, value)
            if peak:
                max_drawdown = max(max_drawdown, (peak - value) / peak)
        total_trades = len(trades)
        return BacktestMetrics(
            total_trades=total_trades,
            win_rate=(len(wins) / total_trades) if total_trades else 0.0,
            profit_factor=(total_profit / total_loss) if total_loss else (float("inf") if total_profit > 0 else 0.0),
            max_drawdown=max_drawdown,
            average_win=(sum(wins) / len(wins)) if wins else 0.0,
            average_loss=(sum(losses) / len(losses)) if losses else 0.0,
            expectancy=(sum(trade.pnl for trade in trades) / total_trades) if total_trades else 0.0,
            no_trade_percentage=(no_trade_count / opportunities) if opportunities else 0.0,
        )
