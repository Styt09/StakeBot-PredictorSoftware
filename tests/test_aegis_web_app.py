from datetime import UTC, datetime, timedelta

from institutional_trading_platform import (
    AegisQuantPlatform,
    AssetClass,
    DATA_UNAVAILABLE,
    Instrument,
    MarketBar,
    SignalQualityEngine,
    TradeDecision,
    ValidationStatus,
    Venue,
)
from institutional_trading_platform.web_app import (
    HTML,
    _live_order_preview,
    _live_order_submit,
    _live_readiness,
    _market_history,
    _market_quote,
    _market_watchlist,
    _set_kill_switch,
)


def _bars(close_step: float = 1.0) -> dict[str, tuple[MarketBar, ...]]:
    instrument = Instrument("TEST", Venue.NSE, AssetClass.EQUITY)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    data = {}
    for timeframe in SignalQualityEngine.REQUIRED_TIMEFRAMES:
        rows = []
        for index in range(24):
            close = 100 + index * close_step
            rows.append(
                MarketBar(
                    instrument=instrument,
                    timestamp=now + timedelta(minutes=index),
                    open=close - 0.2,
                    high=close + 0.5,
                    low=close - 0.5,
                    close=close,
                    volume=10_000 + index * 200,
                    source="unit_test_feed",
                    received_at=now + timedelta(minutes=index, seconds=1),
                )
            )
        data[timeframe] = tuple(rows)
    return data


def _clear_zerodha_env(monkeypatch) -> None:
    for key in (
        "ZERODHA_API_KEY",
        "ZERODHA_API_SECRET",
        "ZERODHA_ACCESS_TOKEN",
        "ZERODHA_EXPECTED_USER_ID",
        "ZERODHA_USER_ID",
        "ZERODHA_INSTRUMENT_DUMP_PATH",
        "LIVE_TRADING_ENABLED",
        "MANUAL_LIVE_APPROVAL_REQUIRED",
        "KILL_SWITCH_ENABLED",
    ):
        monkeypatch.delenv(key, raising=False)


def test_signal_quality_blocks_when_timeframes_missing() -> None:
    output = SignalQualityEngine().evaluate({})

    assert output.decision == TradeDecision.NO_TRADE
    assert output.entry == DATA_UNAVAILABLE
    assert output.provenance.validation_status == ValidationStatus.DATA_UNAVAILABLE
    assert "data_source" in output.provenance.as_dict()
    assert "data_timestamp" in output.provenance.as_dict()
    assert "validation_status" in output.provenance.as_dict()


def test_signal_quality_emits_validated_buy_from_complete_real_bars() -> None:
    output = SignalQualityEngine().evaluate(_bars())

    assert output.decision == TradeDecision.BUY
    assert output.provenance.data_source == "unit_test_feed"
    assert output.provenance.validation_status == ValidationStatus.VALIDATED
    assert output.risk_reward != DATA_UNAVAILABLE
    assert output.confidence != DATA_UNAVAILABLE


def test_aegis_platform_runs_phases_2_through_24_sequentially() -> None:
    phases = AegisQuantPlatform().run(_bars())

    assert [phase.phase for phase in phases] == list(range(2, 25))
    assert phases[0].name == "Signal Quality Engine"
    assert phases[-1].outputs["decision"] == "NO_TRADE"
    for phase in phases:
        payload = phase.as_dict()
        assert payload["provenance"]["data_source"]
        assert payload["provenance"]["data_timestamp"]
        assert payload["provenance"]["validation_status"]


def test_web_app_html_contains_alpha_gate_dashboard_contract() -> None:
    assert "ALPHA-GATE X SHADOW TRADING PLATFORM" in HTML
    assert "Real Live Trading Control Panel" in HTML
    assert "Live Market Dashboard" in HTML
    assert "market-chart" in HTML
    assert "ZERODHA LIVE DATA WHEN CONNECTED" in HTML
    assert "DATA_UNAVAILABLE" in HTML
    assert "/api/demo" in HTML
    assert "/api/shadow/status" in HTML
    assert "/api/market/watchlist" in HTML
    assert "/api/market/quote" in HTML
    assert "/api/market/history" in HTML


def test_market_watchlist_is_safe_without_live_credentials(monkeypatch) -> None:
    _clear_zerodha_env(monkeypatch)
    payload = _market_watchlist()

    assert "RELIANCE" in payload["symbols"]
    assert payload["validation_status"] == "DATA_UNAVAILABLE"
    assert payload["go_live_allowed"] is False


def test_market_quote_returns_data_unavailable_without_fabricated_price(monkeypatch) -> None:
    _clear_zerodha_env(monkeypatch)
    payload = _market_quote("RELIANCE")

    assert payload["symbol"] == "RELIANCE"
    assert payload["ltp"] == "DATA_UNAVAILABLE"
    assert payload["data_source"] == "DATA_UNAVAILABLE"
    assert payload["go_live_allowed"] is False


def test_market_history_returns_empty_chart_state_without_fabrication(monkeypatch) -> None:
    _clear_zerodha_env(monkeypatch)
    payload = _market_history("RELIANCE")

    assert payload["symbol"] == "RELIANCE"
    assert payload["candles"] == ()
    assert payload["validation_status"] == "DATA_UNAVAILABLE"
    assert payload["go_live_allowed"] is False


def test_live_readiness_fails_closed_by_default(monkeypatch) -> None:
    _clear_zerodha_env(monkeypatch)
    readiness = _live_readiness()

    assert readiness["mode"] == "LIVE_MANUAL_APPROVAL_ONLY"
    assert readiness["go_live_allowed"] is False
    assert readiness["live_trading_env_enabled"] is False
    assert "LIVE_TRADING_ENABLED is not true" in readiness["block_reasons"]


def test_live_order_preview_blocks_without_gates(monkeypatch) -> None:
    _clear_zerodha_env(monkeypatch)
    preview = _live_order_preview({"symbol": "RELIANCE", "exchange": "NSE", "side": "BUY", "quantity": 1, "order_type": "LIMIT", "price": 1, "product": "MIS"})

    assert preview["safety_gate_result"] == "BLOCKED"
    assert preview["can_submit_live_order"] is False
    assert preview["go_live_allowed"] is False


def test_live_order_submit_blocks_without_valid_preview(monkeypatch) -> None:
    _clear_zerodha_env(monkeypatch)
    result = _live_order_submit({"preview_id": "missing", "typed_confirmation": "CONFIRM_LIVE_ORDER", "approval_mode": True})

    assert result["status"] == "BLOCKED"
    assert result["broker_order_id"] is None
    assert result["go_live_allowed"] is False


def test_kill_switch_blocks_live_readiness(monkeypatch) -> None:
    _clear_zerodha_env(monkeypatch)
    _set_kill_switch(True)
    try:
        readiness = _live_readiness()
        assert readiness["kill_switch_status"] == "ENABLED"
        assert "kill switch enabled" in readiness["block_reasons"]
    finally:
        _set_kill_switch(False)
