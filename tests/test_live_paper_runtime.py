from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from institutional_trading_platform.alpha_gate_x import AlphaSignal, RiskStatus, TradingMode
from institutional_trading_platform.alpha_gate_x_indicators import ConfidenceGrade, IndicatorSignalOutput, TradingProfile
from institutional_trading_platform.market_data_spine import CandleTimeframe, Tick
from institutional_trading_platform.paper_trading import PaperBroker, PaperOrder, PaperPortfolio, PaperRiskMonitor
from institutional_trading_platform.runtime import LivePaperTradingEngine, RuntimeConfig, RuntimeEventType, RuntimeRecommendation
from institutional_trading_platform.validation import GoLiveGateConfig, build_risk_report, calculate_performance_metrics, evaluate_go_live_gate

UTC = timezone.utc


class StubComposer:
    def __init__(self, signal: AlphaSignal = AlphaSignal.HOLD, correlation_id: str = "corr-1") -> None:
        self.signal = signal
        self.correlation_id = correlation_id
        self.calls = 0

    def intraday_signal(self, **kwargs):
        self.calls += 1
        return IndicatorSignalOutput(
            symbol=kwargs["symbol"],
            timeframe="5m",
            trading_profile=TradingProfile.INTRADAY,
            signal=self.signal,
            final_score=0.8 if self.signal == AlphaSignal.BUY else (-0.8 if self.signal == AlphaSignal.SELL else 0.0),
            confidence=0.85,
            confidence_grade=ConfidenceGrade.A,
            entry_reference=100.0,
            stop_loss=99.0 if self.signal == AlphaSignal.BUY else 101.0,
            target_1=102.0 if self.signal == AlphaSignal.BUY else 98.0,
            target_2=103.0 if self.signal == AlphaSignal.BUY else 97.0,
            expected_move=1.0,
            risk_status=RiskStatus.PASS,
            component_scores={},
            unavailable_components=(),
            reasons=("stub",),
            correlation_id=self.correlation_id,
        )


def _tick(minute: int, price: float = 100.0, symbol: str = "RELIANCE", tick_id: str | None = None) -> Tick:
    return Tick(symbol, "NSE", datetime(2026, 1, 5, 9, 15, tzinfo=UTC) + timedelta(minutes=minute), price, 1000, tick_id=tick_id)


def _engine(signal: AlphaSignal = AlphaSignal.HOLD, correlation_id: str = "corr-1") -> LivePaperTradingEngine:
    return LivePaperTradingEngine(config=RuntimeConfig(allowed_symbols=("RELIANCE",)), composer=StubComposer(signal, correlation_id))


def test_runtime_starts_in_paper_and_rejects_live_auto() -> None:
    assert RuntimeConfig().trading_mode == TradingMode.PAPER_TRADING
    with pytest.raises(ValueError, match="PAPER_TRADING only"):
        RuntimeConfig(trading_mode=TradingMode.LIVE_AUTO)


def test_tick_updates_builder_and_incomplete_candle_does_not_signal() -> None:
    engine = _engine(AlphaSignal.BUY)
    engine.on_tick(_tick(0, 100, tick_id="a"))

    assert engine.candle_builder.current_candle("RELIANCE", "NSE", CandleTimeframe.ONE_MINUTE) is not None
    assert engine.signals_generated == 0
    assert engine.composer.calls == 0


def test_finalized_entry_candle_triggers_signal_and_hold_creates_no_order() -> None:
    engine = _engine(AlphaSignal.HOLD)
    engine.on_tick(_tick(0, tick_id="a"))
    engine.on_tick(_tick(5, tick_id="b"))

    assert engine.signals_generated == 1
    assert engine.signal_counts[AlphaSignal.HOLD.value] == 1
    assert not engine.paper_broker.order_book


def test_no_trade_creates_no_order() -> None:
    engine = _engine(AlphaSignal.NO_TRADE)
    engine.on_tick(_tick(0, tick_id="a"))
    engine.on_tick(_tick(5, tick_id="b"))

    assert engine.signals_generated == 1
    assert not engine.paper_broker.order_book


def test_buy_and_sell_create_virtual_paper_orders_only() -> None:
    buy = _engine(AlphaSignal.BUY, "buy-1")
    buy.on_tick(_tick(0, tick_id="a"))
    buy.on_tick(_tick(5, tick_id="b"))

    sell = _engine(AlphaSignal.SELL, "sell-1")
    sell.on_tick(_tick(0, tick_id="c"))
    sell.on_tick(_tick(5, tick_id="d"))

    assert buy.paper_broker.order_book[0].fill is not None
    assert sell.paper_broker.order_book[0].fill is not None
    assert buy.paper_broker.order_book[0].order_id.startswith("paper-")
    assert sell.paper_broker.order_book[0].order_id.startswith("paper-")


def test_duplicate_signal_order_prevention() -> None:
    engine = _engine(AlphaSignal.BUY, "same-correlation")
    for minute, tick_id in [(0, "a"), (5, "b"), (10, "c")]:
        engine.on_tick(_tick(minute, tick_id=tick_id))

    assert len([order for order in engine.paper_broker.order_book if order.fill is not None]) == 1
    assert any("duplicate" in event.payload.get("reasons", ("",))[0] for event in engine.audit_store.by_event_type(RuntimeEventType.RISK_BLOCKED))


def test_paper_market_order_fill_brokerage_slippage_realized_and_unrealized_pnl() -> None:
    portfolio = PaperPortfolio(initial_capital=10_000, max_open_positions=2)
    broker = PaperBroker(portfolio, brokerage_per_order=10, slippage_percent=1.0)
    result = broker.place_order(PaperOrder("corr", "RELIANCE", AlphaSignal.BUY, 2, stop_loss=95, target_1=110), 100, _tick(0).timestamp)

    assert result.fill is not None
    assert result.fill.price == 101
    assert portfolio.cash_balance == 9990
    assert portfolio.unrealized_pnl({"RELIANCE": 105}) == 8
    closed = broker.check_exits("RELIANCE", high=111, low=100, close=110, timestamp=_tick(1).timestamp)[0]
    assert closed.pnl == ((110 * 0.99) - 101) * 2 - 10
    assert portfolio.realized_pnl == closed.pnl


def test_paper_stop_loss_trigger() -> None:
    portfolio = PaperPortfolio(initial_capital=10_000, max_open_positions=2)
    broker = PaperBroker(portfolio, brokerage_per_order=0, slippage_percent=0)
    broker.place_order(PaperOrder("corr", "RELIANCE", AlphaSignal.BUY, 1, stop_loss=99, target_1=110), 100, _tick(0).timestamp)

    closed = broker.check_exits("RELIANCE", high=101, low=98, close=99, timestamp=_tick(1).timestamp)

    assert closed[0].exit_price == 99
    assert closed[0].pnl == -1


def test_daily_loss_max_trades_kill_switch_and_stale_feed_blocks() -> None:
    portfolio = PaperPortfolio(initial_capital=10_000, max_open_positions=2)
    monitor = PaperRiskMonitor(portfolio, 10_000, max_daily_loss_percent=1, max_trades_per_day=1)
    portfolio.closed_positions.append(type("Closed", (), {"pnl": -100, "closed_at": _tick(0).timestamp, "symbol": "RELIANCE"})())
    approved, reasons = monitor.assess(timestamp=_tick(0).timestamp)
    assert not approved and "daily loss limit hit" in reasons

    monitor = PaperRiskMonitor(PaperPortfolio(initial_capital=10_000), 10_000, max_trades_per_day=1)
    monitor.record_trade()
    assert "max trades per day hit" in monitor.assess(timestamp=_tick(0).timestamp)[1]
    monitor.kill_switch_active = True
    assert "kill switch active" in monitor.assess(timestamp=_tick(0).timestamp, stale_data=True)[1]
    assert "stale data block" in monitor.assess(timestamp=_tick(0).timestamp, stale_data=True)[1]


def test_stale_tick_blocks_and_audit_query_by_correlation_id() -> None:
    engine = _engine(AlphaSignal.BUY, "corr-audit")
    received_at = _tick(0).timestamp + timedelta(seconds=10)
    engine.on_tick(_tick(0, tick_id="old"), received_at=received_at)

    assert engine.data_quality_blocks == 1
    assert engine.audit_store.by_event_type(RuntimeEventType.RISK_BLOCKED)

    engine.on_tick(_tick(1, tick_id="a"))
    engine.on_tick(_tick(5, tick_id="b"))
    chain = engine.audit_store.by_correlation_id("corr-audit")
    assert {event.event_type for event in chain} >= {RuntimeEventType.SIGNAL_GENERATED, RuntimeEventType.PAPER_ORDER_CREATED, RuntimeEventType.PAPER_ORDER_FILLED, RuntimeEventType.PAPER_POSITION_OPENED, RuntimeEventType.PAPER_PNL_UPDATED}
    assert "corr-audit" in engine.audit_store.export_json()


def test_end_of_day_square_off_runtime_report_and_validation_conversion() -> None:
    engine = _engine(AlphaSignal.BUY, "square")
    engine.on_tick(_tick(0, 100, tick_id="a"))
    engine.on_tick(_tick(5, 100, tick_id="b"))
    engine.on_tick(Tick("RELIANCE", "NSE", datetime(2026, 1, 5, 9, 46, tzinfo=UTC), 101, 1000, tick_id="close"))

    report = engine.build_report(datetime(2026, 1, 5, 10, 1, tzinfo=UTC))
    validation = engine.to_validation_report(datetime(2026, 1, 5, 10, 1, tzinfo=UTC))

    assert report.closed_positions == 1
    assert report.go_live_allowed is False
    assert report.recommendation in {RuntimeRecommendation.CONTINUE_PAPER, RuntimeRecommendation.FAIL}
    assert validation.go_live_allowed is False


def test_max_ticks_per_second_guard_blocks_runtime_burst() -> None:
    engine = LivePaperTradingEngine(config=RuntimeConfig(allowed_symbols=("RELIANCE",), max_ticks_per_second=1), composer=StubComposer(AlphaSignal.HOLD))
    engine.on_tick(_tick(0, tick_id="burst-1"))
    second = Tick("RELIANCE", "NSE", _tick(0).timestamp, 100.1, 1000, tick_id="burst-2")
    engine.on_tick(second)

    assert any("max ticks per second exceeded" in event.payload.get("reasons", ()) for event in engine.audit_store.by_event_type(RuntimeEventType.RISK_BLOCKED))


def test_validation_report_consistency_no_low_trade_failure_when_threshold_met() -> None:
    trades = tuple(
        __import__("institutional_trading_platform.market_data_spine", fromlist=["TradeRecord"]).TradeRecord(
            "RELIANCE", AlphaSignal.BUY, _tick(i).timestamp, _tick(i).timestamp + timedelta(minutes=1), 100, 101, 1, 1
        )
        for i in range(100)
    )
    metrics = calculate_performance_metrics(trades, (100_000,) + tuple(100_001 + i for i in range(100)), initial_capital=100_000, opportunities=120, no_trade_count=20)
    gate = evaluate_go_live_gate(metrics, build_risk_report(()), config=GoLiveGateConfig(minimum_trades=100, minimum_profit_factor=0, minimum_win_rate=0, maximum_drawdown_pct=100, minimum_no_trade_percentage=0))

    assert not any("total trades" in reason and "below minimum" in reason for reason in gate.failure_reasons)
