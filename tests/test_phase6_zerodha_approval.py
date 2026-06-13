from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from institutional_trading_platform.alpha_gate_x import AlphaSignal, RiskStatus, TradingMode
from institutional_trading_platform.alpha_gate_x_indicators import ConfidenceGrade, IndicatorSignalOutput, TradingProfile
from institutional_trading_platform.broker import (
    ApprovalModeService,
    ApprovalStatus,
    ApprovedTradePlan,
    BrokerPositionSnapshot,
    BrokerReconciliationService,
    BrokerStateSnapshot,
    ExitReason,
    InstrumentResolutionStatus,
    LocalApprovalState,
    RealOrderSafetyStatus,
    SLTargetMonitor,
    ZerodhaAuthConfig,
    ZerodhaAuthService,
    ZerodhaConnectionStatus,
    ZerodhaInstrumentManager,
    ZerodhaOrderSafetyWrapper,
    ZerodhaWebSocketMarketDataAdapter,
)
from institutional_trading_platform.market_data_spine import CandleTimeframe, Tick
from institutional_trading_platform.runtime import EventBus, LivePaperTradingEngine, RuntimeConfig, RuntimeEventType

UTC = timezone.utc


def _signal(signal: AlphaSignal = AlphaSignal.BUY, correlation_id: str = "sig-1") -> IndicatorSignalOutput:
    return IndicatorSignalOutput(
        symbol="RELIANCE",
        timeframe="5m",
        trading_profile=TradingProfile.INTRADAY,
        signal=signal,
        final_score=0.8,
        confidence=0.9,
        confidence_grade=ConfidenceGrade.A,
        entry_reference=100.0,
        stop_loss=99.0,
        target_1=102.0,
        target_2=103.0,
        expected_move=1.0,
        risk_status=RiskStatus.PASS,
        component_scores={},
        unavailable_components=(),
        reasons=("test",),
        correlation_id=correlation_id,
    )


class HoldComposer:
    calls = 0

    def intraday_signal(self, **kwargs):
        self.calls += 1
        return _signal(AlphaSignal.HOLD, "hold-1")


def _tick(minute: int, tick_id: str, price: float = 100.0) -> Tick:
    return Tick("RELIANCE", "NSE", datetime(2026, 1, 5, 9, 15, tzinfo=UTC) + timedelta(minutes=minute), price, 1000, tick_id=tick_id)


def test_missing_zerodha_credentials_blocks_safely() -> None:
    bus = EventBus()
    state = ZerodhaAuthService(ZerodhaAuthConfig(api_key="", access_token=""), event_bus=bus).validate()

    assert state.status == ZerodhaConnectionStatus.ZERODHA_UNAVAILABLE
    assert "ZERODHA_API_KEY missing" in state.reasons
    assert "ZERODHA_ACCESS_TOKEN missing" in state.reasons
    assert bus.events[-1].event_type == RuntimeEventType.ZERODHA_AUTH_FAILED


def test_instrument_token_resolution_and_unknown_symbol_failure() -> None:
    bus = EventBus()
    manager = ZerodhaInstrumentManager.from_csv(
        "instrument_token,exchange,tradingsymbol,segment,lot_size,tick_size\n123,NSE,RELIANCE,NSE,1,0.05\n",
        event_bus=bus,
    )

    resolved = manager.resolve("RELIANCE")
    unknown = manager.resolve("UNKNOWN")

    assert resolved.status == InstrumentResolutionStatus.RESOLVED
    assert resolved.instrument is not None and resolved.instrument.instrument_token == 123
    assert unknown.status == InstrumentResolutionStatus.NOT_FOUND
    assert bus.events[-1].event_type == RuntimeEventType.INSTRUMENT_RESOLUTION_FAILED


def test_websocket_tick_maps_to_internal_tick_and_emits_event() -> None:
    bus = EventBus()
    adapter = ZerodhaWebSocketMarketDataAdapter({123: ("RELIANCE", "NSE")}, event_bus=bus)
    exchange_ts = datetime(2026, 1, 5, 9, 15, tzinfo=UTC)

    result = adapter.map_tick({"instrument_token": 123, "last_price": 2500.5, "exchange_timestamp": exchange_ts, "volume_traded": 10})

    assert result.ok
    assert result.tick == Tick("RELIANCE", "NSE", exchange_ts, 2500.5, 10, tick_id="123-2026-01-05T09:15:00+00:00")
    assert bus.events[-1].event_type == RuntimeEventType.ZERODHA_TICK_RECEIVED


def test_stale_tick_blocks_signal_and_incomplete_candle_does_not_signal() -> None:
    composer = HoldComposer()
    engine = LivePaperTradingEngine(config=RuntimeConfig(allowed_symbols=("RELIANCE",)), composer=composer)
    old_tick = _tick(0, "old")
    engine.on_tick(old_tick, received_at=old_tick.timestamp + timedelta(seconds=10))

    assert engine.data_quality_blocks == 1
    assert composer.calls == 0

    engine.on_tick(_tick(1, "fresh"))
    assert composer.calls == 0


def test_finalized_candle_can_signal() -> None:
    composer = HoldComposer()
    engine = LivePaperTradingEngine(config=RuntimeConfig(allowed_symbols=("RELIANCE",)), composer=composer)

    engine.on_tick(_tick(0, "a"))
    engine.on_tick(_tick(5, "b"))

    assert composer.calls == 1
    assert engine.signals_generated == 1
    assert engine.candle_builder.completed_candles("RELIANCE", "NSE", CandleTimeframe.FIVE_MINUTES)


def test_reconciliation_pass_allows_approval_request_and_fail_blocks() -> None:
    bus = EventBus()
    recon = BrokerReconciliationService(event_bus=bus)
    now = datetime(2026, 1, 5, 9, 15, tzinfo=UTC)
    recon.reconcile(BrokerStateSnapshot(updated_at=now), LocalApprovalState(), now=now)
    wrapper = ZerodhaOrderSafetyWrapper(event_bus=bus)
    service = ApprovalModeService(RuntimeConfig(trading_mode=TradingMode.APPROVAL_REQUIRED), recon, wrapper, event_bus=bus)

    request = service.request_approval(_signal())
    decision = service.approve(request, user_approved=True)

    assert request.status == ApprovalStatus.APPROVAL_REQUIRED
    assert decision.preview is not None
    assert bus.events[-2].event_type == RuntimeEventType.ZERODHA_ORDER_PREVIEW_GENERATED

    failed_recon = BrokerReconciliationService(event_bus=bus)
    failed_recon.reconcile(BrokerStateSnapshot(positions=(BrokerPositionSnapshot("RELIANCE", 1, 100.0),), updated_at=now), LocalApprovalState(), now=now)
    blocked = ApprovalModeService(RuntimeConfig(trading_mode=TradingMode.APPROVAL_REQUIRED), failed_recon, wrapper, event_bus=bus).request_approval(_signal(correlation_id="blocked"))

    assert blocked.status == ApprovalStatus.BLOCKED
    assert "unexpected open position RELIANCE" in blocked.reasons


def test_approval_required_creates_preview_only_and_real_order_blocked() -> None:
    bus = EventBus()
    wrapper = ZerodhaOrderSafetyWrapper(event_bus=bus)
    preview = wrapper.preview(correlation_id="corr", symbol="RELIANCE", exchange="NSE", side=AlphaSignal.BUY, quantity=1, price=100, stop_loss=99, target=102, risk_amount=1)
    result = wrapper.submit_real_order(preview)

    assert preview.symbol == "RELIANCE"
    assert result.status == RealOrderSafetyStatus.NO_REAL_ORDER_PLACED
    assert bus.events[-1].event_type == RuntimeEventType.REAL_ORDER_BLOCKED


def test_live_auto_is_rejected_and_go_live_allowed_remains_false() -> None:
    with pytest.raises(ValueError, match="rejects LIVE_AUTO"):
        RuntimeConfig(trading_mode=TradingMode.LIVE_AUTO)

    report = LivePaperTradingEngine(config=RuntimeConfig()).build_report()
    assert report.go_live_allowed is False


def test_sl_target_monitor_emits_exit_suggested_preview_without_auto_exit() -> None:
    bus = EventBus()
    wrapper = ZerodhaOrderSafetyWrapper(event_bus=bus)
    monitor = SLTargetMonitor(wrapper, event_bus=bus)
    monitor.track(ApprovedTradePlan("plan-1", "RELIANCE", "NSE", AlphaSignal.BUY, 1, 100, 99, 102))

    suggestions = monitor.on_ltp("RELIANCE", 102.5)

    assert suggestions[0].reason == ExitReason.TARGET
    assert suggestions[0].preview is not None
    assert any(event.event_type == RuntimeEventType.EXIT_SUGGESTED for event in bus.events)
