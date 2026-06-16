"""Live-like PAPER_TRADING runtime for ALPHA-GATE X Phase 5."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import StrEnum

from ..alpha_gate_x import AlphaSignal, RiskDecision, RiskStatus, TradingMode
from ..alpha_gate_x_indicators import IndicatorContext, IndicatorSignalComposer, IndicatorSignalOutput, TradingProfile
from ..market_data_spine import CandleBuilder, CandleTimeframe, DataQualityChecker, DataQualityStatus, OHLCVCandle, Tick, TradeRecord
from ..paper_trading import PaperBroker, PaperOrder, PaperPortfolio, PaperRiskMonitor
from ..validation import build_equity_curve, build_risk_report, calculate_performance_metrics, create_validation_report
from ..validation.risk_report import RiskEventRecord
from ..validation.validation_report import ValidationReport
from .audit_store import InMemoryAuditStore
from .event_bus import EventBus, RuntimeEvent, RuntimeEventType
from .runtime_config import RuntimeConfig
from .session_manager import SessionManager


class RuntimeRecommendation(StrEnum):
    CONTINUE_PAPER = "CONTINUE_PAPER"
    READY_FOR_APPROVAL_MODE = "READY_FOR_APPROVAL_MODE"
    FAIL = "FAIL"


@dataclass(frozen=True)
class LivePaperRuntimeReport:
    start_time: datetime
    end_time: datetime
    symbols: tuple[str, ...]
    total_ticks_processed: int
    candles_finalized: int
    signals_generated: int
    signal_counts: dict[str, int]
    paper_orders: int
    fills: int
    open_positions: int
    closed_positions: int
    realized_pnl: float
    unrealized_pnl: float
    total_equity: float
    max_drawdown: float
    risk_blocks: int
    data_quality_blocks: int
    runtime_errors: int
    recommendation: RuntimeRecommendation
    go_live_allowed: bool = False


@dataclass
class LivePaperTradingEngine:
    config: RuntimeConfig = field(default_factory=RuntimeConfig)
    composer: IndicatorSignalComposer = field(default_factory=IndicatorSignalComposer)
    event_bus: EventBus = field(default_factory=EventBus)
    audit_store: InMemoryAuditStore = field(default_factory=InMemoryAuditStore)

    def __post_init__(self) -> None:
        if self.config.trading_mode != TradingMode.PAPER_TRADING:
            raise ValueError("LivePaperTradingEngine is paper-only and rejects LIVE_AUTO")
        self.candle_builder = CandleBuilder(self.config.allowed_timeframes)
        self.data_quality = DataQualityChecker(stale_after=self.config.stale_feed_timeout)
        self.portfolio = PaperPortfolio(self.config.paper_initial_capital, self.config.paper_initial_capital, max_open_positions=self.config.max_open_positions)
        self.paper_broker = PaperBroker(self.portfolio, self.config.brokerage_per_order, self.config.slippage_percent)
        self.risk_monitor = PaperRiskMonitor(self.portfolio, self.config.paper_initial_capital, max_daily_loss_percent=self.config.max_daily_loss_percent, max_trades_per_day=self.config.max_trades_per_day, max_open_positions=self.config.max_open_positions, max_exposure_percent=self.config.max_exposure_percent)
        self.session_manager = SessionManager(self.config.session_start, self.config.session_end, self.config.square_off_time, self.config.timezone_name)
        self.started_at = datetime.now(timezone.utc)
        self.total_ticks_processed = 0
        self.candles_finalized = 0
        self.signals_generated = 0
        self.signal_counts = {signal.value: 0 for signal in AlphaSignal}
        self.risk_blocks: list[RiskEventRecord] = []
        self.data_quality_blocks = 0
        self.runtime_errors = 0
        self.last_prices: dict[str, float] = {}
        self.equity_curve: list[float] = [self.config.paper_initial_capital]
        self._ordered_correlations: set[str] = set()
        self._tick_second_counts: dict[tuple[str, datetime], int] = {}
        self.event_bus.subscribe(self.audit_store.append)

    def on_tick(self, tick: Tick, received_at: datetime | None = None) -> tuple[RuntimeEvent, ...]:
        emitted_before = len(self.event_bus.events)
        try:
            if tick.symbol not in self.config.allowed_symbols:
                self._risk_block(tick.symbol, None, ("symbol not allowed",))
                return tuple(self.event_bus.events[emitted_before:])
            second_key = (tick.symbol, tick.timestamp.replace(microsecond=0))
            self._tick_second_counts[second_key] = self._tick_second_counts.get(second_key, 0) + 1
            if self._tick_second_counts[second_key] > self.config.max_ticks_per_second:
                self._risk_block(tick.symbol, None, ("max ticks per second exceeded",))
                return tuple(self.event_bus.events[emitted_before:])
            self.total_ticks_processed += 1
            self.last_prices[tick.symbol] = tick.price
            self._emit(RuntimeEventType.TICK_RECEIVED, tick.symbol, {"price": tick.price, "quantity": tick.quantity})
            quality = self.data_quality.check_tick(tick, received_at or tick.timestamp)
            if quality.status == DataQualityStatus.FAIL:
                self.data_quality_blocks += 1
                self._risk_block(tick.symbol, None, quality.reasons)
                return tuple(self.event_bus.events[emitted_before:])
            finalized = self.candle_builder.update_tick(tick)
            for candle in finalized:
                self.candles_finalized += 1
                self._emit(RuntimeEventType.CANDLE_FINALIZED, candle.symbol, {"timeframe": candle.timeframe.value, "close": candle.close})
                for closed in self.paper_broker.check_exits(candle.symbol, candle.high, candle.low, candle.close, candle.end):
                    self._emit(RuntimeEventType.PAPER_POSITION_CLOSED, closed.symbol, {"pnl": closed.pnl}, closed.correlation_id)
                    self._pnl_update(candle.end, closed.correlation_id)
                if candle.timeframe == self._entry_timeframe():
                    self._generate_and_route(candle)
            if self.session_manager.should_square_off(tick.timestamp):
                for closed in self.paper_broker.square_off_all(self.last_prices, tick.timestamp):
                    self._emit(RuntimeEventType.PAPER_POSITION_CLOSED, closed.symbol, {"pnl": closed.pnl, "reason": "square_off"}, closed.correlation_id)
                    self._pnl_update(tick.timestamp, closed.correlation_id)
        except Exception as exc:  # runtime fail-safe event, not import guard
            self.runtime_errors += 1
            self._emit(RuntimeEventType.RUNTIME_ERROR, tick.symbol, {"error": str(exc)})
        return tuple(self.event_bus.events[emitted_before:])

    def heartbeat(self, timestamp: datetime | None = None) -> RuntimeEvent:
        return self._emit(RuntimeEventType.RUNTIME_HEARTBEAT, None, {"total_ticks": self.total_ticks_processed}, timestamp=timestamp)

    def build_report(self, end_time: datetime | None = None) -> LivePaperRuntimeReport:
        end_time = end_time or datetime.now(timezone.utc)
        metrics = calculate_performance_metrics(self.paper_broker.closed_trades(), tuple(self.equity_curve), initial_capital=self.config.paper_initial_capital)
        recommendation = RuntimeRecommendation.CONTINUE_PAPER
        if self.runtime_errors:
            recommendation = RuntimeRecommendation.FAIL
        elif metrics.total_trades >= self.config.ready_for_approval_min_trades and metrics.profit_factor >= self.config.ready_for_approval_min_profit_factor:
            recommendation = RuntimeRecommendation.READY_FOR_APPROVAL_MODE
        return LivePaperRuntimeReport(
            self.started_at,
            end_time,
            self.config.allowed_symbols,
            self.total_ticks_processed,
            self.candles_finalized,
            self.signals_generated,
            dict(self.signal_counts),
            len(self.paper_broker.order_book),
            sum(1 for order in self.paper_broker.order_book if order.fill is not None),
            len(self.portfolio.open_positions),
            len(self.portfolio.closed_positions),
            self.portfolio.realized_pnl,
            self.portfolio.unrealized_pnl(self.last_prices),
            self.portfolio.total_equity(self.last_prices),
            metrics.max_drawdown,
            len(self.risk_blocks),
            self.data_quality_blocks,
            self.runtime_errors,
            recommendation,
            False,
        )

    def to_validation_report(self, end_time: datetime | None = None) -> ValidationReport:
        trades = self.paper_broker.closed_trades()
        equity = tuple(self.equity_curve) if self.equity_curve else build_equity_curve(self.config.paper_initial_capital, trades)
        metrics = calculate_performance_metrics(trades, equity, initial_capital=self.config.paper_initial_capital)
        risk_report = build_risk_report(tuple(self.risk_blocks))
        start = self.started_at
        end = end_time or datetime.now(timezone.utc)
        report = create_validation_report(
            strategy_name="ALPHA-GATE X Phase 5 Paper Runtime",
            trading_profile=self.config.trading_profile.value,
            symbols=self.config.allowed_symbols,
            timeframe=self._entry_timeframe().value,
            start_date=start,
            end_date=end,
            initial_capital=self.config.paper_initial_capital,
            metrics=metrics,
            equity_curve=equity,
            walk_forward_results=None,
            regime_analysis={},
            symbol_analysis={},
            time_analysis={},
            risk_report=risk_report,
        )
        return ValidationReport(**{**report.__dict__, "go_live_allowed": False, "recommendations": report.recommendations + ("Phase 5 can only recommend PAPER_TRADING or APPROVAL_MODE, never LIVE_AUTO",)})

    def _generate_and_route(self, candle: OHLCVCandle) -> None:
        approved, reasons = self.risk_monitor.assess(timestamp=candle.end, prices=self.last_prices)
        if self._first_five_minutes_blocked(candle.end):
            reasons = reasons + ("first 5 minutes blocked",)
            approved = False
        if not approved:
            self._risk_block(candle.symbol, None, reasons)
            return
        risk = RiskDecision(RiskStatus.PASS, 1, 0.0, ())
        signal = self._compose_signal(candle, risk)
        self.signals_generated += 1
        self.signal_counts[signal.signal.value] += 1
        self._emit(RuntimeEventType.SIGNAL_GENERATED, candle.symbol, {"signal": signal.signal.value, "confidence": signal.confidence}, signal.correlation_id)
        if signal.signal in {AlphaSignal.HOLD, AlphaSignal.NO_TRADE}:
            return
        if signal.correlation_id in self._ordered_correlations:
            self._risk_block(candle.symbol, signal.correlation_id, ("duplicate signal/order prevented",))
            return
        self._ordered_correlations.add(signal.correlation_id)
        order = PaperOrder(signal.correlation_id, candle.symbol, signal.signal, max(1, risk.quantity), requested_price=signal.entry_reference, stop_loss=signal.stop_loss, target_1=signal.target_1, target_2=signal.target_2)
        self._emit(RuntimeEventType.PAPER_ORDER_CREATED, candle.symbol, {"side": signal.signal.value, "quantity": order.quantity}, signal.correlation_id)
        result = self.paper_broker.place_order(order, candle.close, candle.end, risk_approved=True)
        if result.fill is not None:
            self.risk_monitor.record_trade()
            self._emit(RuntimeEventType.PAPER_ORDER_FILLED, candle.symbol, {"price": result.fill.price}, signal.correlation_id)
            self._emit(RuntimeEventType.PAPER_POSITION_OPENED, candle.symbol, {"entry_price": result.fill.price}, signal.correlation_id)
            self._pnl_update(candle.end, signal.correlation_id)
        elif result.rejection_reason:
            self._risk_block(candle.symbol, signal.correlation_id, (result.rejection_reason,))


    def _first_five_minutes_blocked(self, timestamp: datetime) -> bool:
        if self.config.enable_first_5_min_trading:
            return False
        local = self.session_manager.localize(timestamp)
        start = datetime.combine(local.date(), self.config.session_start, tzinfo=local.tzinfo)
        return start <= local < start + timedelta(minutes=5)

    def _compose_signal(self, candle: OHLCVCandle, risk: RiskDecision) -> IndicatorSignalOutput:
        ctx = IndicatorContext(depth=None, breadth=None)
        if self.config.trading_profile == TradingProfile.SWING:
            return self.composer.swing_signal(
                symbol=candle.symbol,
                exchange=candle.exchange,
                daily=self.candle_builder.completed_candles(candle.symbol, candle.exchange, CandleTimeframe.DAILY),
                hourly=self.candle_builder.completed_candles(candle.symbol, candle.exchange, CandleTimeframe.ONE_HOUR),
                risk_decision=risk,
                context=ctx,
            )
        return self.composer.intraday_signal(
            symbol=candle.symbol,
            exchange=candle.exchange,
            one_minute=self.candle_builder.completed_candles(candle.symbol, candle.exchange, CandleTimeframe.ONE_MINUTE),
            five_minute=self.candle_builder.completed_candles(candle.symbol, candle.exchange, CandleTimeframe.FIVE_MINUTES),
            fifteen_minute=self.candle_builder.completed_candles(candle.symbol, candle.exchange, CandleTimeframe.FIFTEEN_MINUTES),
            risk_decision=risk,
            context=ctx,
        )

    def _entry_timeframe(self) -> CandleTimeframe:
        return CandleTimeframe.ONE_HOUR if self.config.trading_profile == TradingProfile.SWING else CandleTimeframe.FIVE_MINUTES

    def _risk_block(self, symbol: str, correlation_id: str | None, reasons: tuple[str, ...]) -> None:
        reason_text = "; ".join(reasons)
        self.risk_blocks.append(RiskEventRecord(reason_text))
        self._emit(RuntimeEventType.RISK_BLOCKED, symbol, {"reasons": reasons}, correlation_id)

    def _pnl_update(self, timestamp: datetime, correlation_id: str | None = None) -> None:
        equity = self.portfolio.total_equity(self.last_prices)
        self.equity_curve.append(equity)
        self._emit(RuntimeEventType.PAPER_PNL_UPDATED, None, {"equity": equity, "realized_pnl": self.portfolio.realized_pnl}, correlation_id, timestamp=timestamp)

    def _emit(self, event_type: RuntimeEventType, symbol: str | None, payload: dict[str, object], correlation_id: str | None = None, timestamp: datetime | None = None) -> RuntimeEvent:
        return self.event_bus.publish(RuntimeEvent(event_type=event_type, symbol=symbol, payload=payload, correlation_id=correlation_id, timestamp=timestamp or datetime.now(timezone.utc)))
