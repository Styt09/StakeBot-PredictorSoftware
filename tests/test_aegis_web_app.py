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
from institutional_trading_platform.web_app import HTML


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


def test_web_app_html_contains_alpha_gate_shadow_dashboard_contract() -> None:
    assert "ALPHA-GATE X SHADOW TRADING PLATFORM" in HTML
    assert "Paper Trading → Shadow Trading → Manual Review" in HTML
    assert "Real Shadow Runtime Status" in HTML
    assert "DATA_UNAVAILABLE" in HTML
    assert "/api/demo" in HTML
    assert "/api/shadow/status" in HTML
    assert "Last Action Result" in HTML
    assert "Preview LIMIT Order" in HTML
    assert "Preview required before submit" in HTML
    assert "currentPreviewId" in HTML
    assert "Server restart is required" in HTML


def test_shadow_status_fails_closed_without_broker_inputs(monkeypatch) -> None:
    from institutional_trading_platform.web_app import _shadow_status

    for key in ("ZERODHA_API_KEY", "ZERODHA_ACCESS_TOKEN", "ENABLE_ZERODHA_WEBSOCKET"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("ZERODHA_INSTRUMENT_DUMP_PATH", "data/instruments.csv")

    status = _shadow_status()

    assert status["mode"] == "PAPER_TRADING"
    assert status["go_live_allowed"] is False
    assert status["zerodha_status"] == "ZERODHA_UNAVAILABLE"
    assert status["total_ticks_processed"] == 0
    assert status["shadow_recommendation"] == "CONTINUE_PAPER"
    assert any("missing Zerodha credentials" in reason for reason in status["failure_reasons"])


def test_live_readiness_defaults_to_blocked(monkeypatch) -> None:
    from institutional_trading_platform.web_app import _live_readiness

    for key in (
        "ZERODHA_API_KEY",
        "ZERODHA_API_SECRET",
        "ZERODHA_ACCESS_TOKEN",
        "ZERODHA_EXPECTED_USER_ID",
        "LIVE_TRADING_ENABLED",
        "MANUAL_LIVE_APPROVAL_REQUIRED",
        "KILL_SWITCH_ENABLED",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("ZERODHA_INSTRUMENT_DUMP_PATH", "data/instruments.csv")

    readiness = _live_readiness()

    assert readiness["mode"] == "LIVE_MANUAL_APPROVAL_ONLY"
    assert readiness["go_live_allowed"] is False
    assert readiness["live_trading_env_enabled"] is False
    assert readiness["manual_approval_required"] is False
    assert readiness["kill_switch_status"] == "DISABLED"


def test_live_order_preview_is_limit_only_and_blocked(monkeypatch) -> None:
    from institutional_trading_platform.web_app import _live_order_preview

    for key in ("ZERODHA_API_KEY", "ZERODHA_API_SECRET", "ZERODHA_ACCESS_TOKEN", "LIVE_TRADING_ENABLED", "MANUAL_LIVE_APPROVAL_REQUIRED"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("ZERODHA_INSTRUMENT_DUMP_PATH", "data/instruments.csv")

    preview = _live_order_preview({"symbol": "RELIANCE", "exchange": "NSE", "side": "BUY", "quantity": 1, "order_type": "MARKET", "price": 100.0, "product": "MIS"})

    assert preview["go_live_allowed"] is False
    assert preview["can_submit_live_order"] is False
    assert preview["safety_gate_result"] == "BLOCKED"
    assert "only LIMIT orders are allowed by default" in preview["block_reasons"]


def test_live_order_submit_requires_confirmation_and_blocks(monkeypatch) -> None:
    from institutional_trading_platform.web_app import _live_order_preview, _live_order_submit

    for key in ("ZERODHA_API_KEY", "ZERODHA_API_SECRET", "ZERODHA_ACCESS_TOKEN", "LIVE_TRADING_ENABLED", "MANUAL_LIVE_APPROVAL_REQUIRED"):
        monkeypatch.delenv(key, raising=False)
    preview = _live_order_preview({"symbol": "RELIANCE", "exchange": "NSE", "side": "BUY", "quantity": 1, "order_type": "LIMIT", "price": 100.0, "product": "MIS"})

    result = _live_order_submit({"preview_id": preview["preview_id"], "typed_confirmation": "WRONG", "approval_mode": False})

    assert result["status"] == "BLOCKED"
    assert result["broker_order_id"] is None
    assert result["go_live_allowed"] is False
    assert "typed confirmation mismatch" in result["block_reasons"]


def _enable_live_env(monkeypatch, tmp_path):
    instrument_path = tmp_path / "instruments.csv"
    instrument_path.write_text("instrument_token,exchange,tradingsymbol,segment,lot_size,tick_size\n123,NSE,RELIANCE,NSE,1,0.05\n", encoding="utf-8")
    monkeypatch.setenv("ZERODHA_API_KEY", "key")
    monkeypatch.setenv("ZERODHA_API_SECRET", "secret")
    monkeypatch.setenv("ZERODHA_ACCESS_TOKEN", "token")
    monkeypatch.setenv("ZERODHA_EXPECTED_USER_ID", "TTS544")
    monkeypatch.setenv("ZERODHA_INSTRUMENT_DUMP_PATH", str(instrument_path))
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "true")
    monkeypatch.setenv("MANUAL_LIVE_APPROVAL_REQUIRED", "true")
    monkeypatch.setenv("MAX_LIVE_ORDER_QTY", "1")


class _FakeKiteClient:
    def __init__(self) -> None:
        self.submitted = False

    def margins(self):
        return {"equity": {"available": {"cash": 10000.0}}}

    def place_order(self, **kwargs):
        self.submitted = True
        self.last_order = kwargs
        return "order-123"

    def order_history(self, order_id):
        return [{"order_id": order_id, "status": "OPEN"}]

    def orders(self):
        return [{"order_id": "order-123", "tradingsymbol": "RELIANCE", "exchange": "NSE", "transaction_type": "BUY", "quantity": 1, "status": "OPEN", "order_type": "LIMIT", "product": "MIS", "price": 1.0, "average_price": 0.0}]


def test_live_margin_check_passes_with_fake_client(monkeypatch) -> None:
    from institutional_trading_platform import web_app

    fake = _FakeKiteClient()
    monkeypatch.setattr(web_app, "_kite_client_from_env", lambda: fake)

    result = web_app._live_margin_check(estimated_risk=1.0)

    assert result["status"] == "PASS"
    assert result["available_margin"] == 10000.0
    assert result["go_live_allowed"] is False


def test_live_order_preview_can_pass_with_margin_check(monkeypatch, tmp_path) -> None:
    from institutional_trading_platform import web_app

    _enable_live_env(monkeypatch, tmp_path)
    monkeypatch.setattr(web_app, "_LIVE_KILL_SWITCH_ENABLED", False)
    monkeypatch.setattr(web_app, "_market_hours_valid", lambda now=None: True)
    monkeypatch.setattr(web_app, "_kite_client_from_env", lambda: _FakeKiteClient())

    preview = web_app._live_order_preview({"symbol": "RELIANCE", "exchange": "NSE", "side": "BUY", "quantity": 1, "order_type": "LIMIT", "price": 1.0, "product": "MIS"})

    assert preview["safety_gate_result"] == "PASS"
    assert preview["can_submit_live_order"] is True
    assert preview["margin_check"]["status"] == "PASS"
    assert preview["go_live_allowed"] is False


def test_live_order_submit_requires_real_broker_submit_flag(monkeypatch, tmp_path) -> None:
    from institutional_trading_platform import web_app

    _enable_live_env(monkeypatch, tmp_path)
    monkeypatch.delenv("REAL_BROKER_ORDER_SUBMIT_ENABLED", raising=False)
    monkeypatch.setattr(web_app, "_LIVE_KILL_SWITCH_ENABLED", False)
    monkeypatch.setattr(web_app, "_market_hours_valid", lambda now=None: True)
    monkeypatch.setattr(web_app, "_kite_client_from_env", lambda: _FakeKiteClient())
    preview = web_app._live_order_preview({"symbol": "RELIANCE", "exchange": "NSE", "side": "BUY", "quantity": 1, "order_type": "LIMIT", "price": 1.0, "product": "MIS"})

    result = web_app._live_order_submit({"preview_id": preview["preview_id"], "typed_confirmation": "CONFIRM_LIVE_ORDER", "approval_mode": True})

    assert result["status"] == "BLOCKED"
    assert result["broker_order_id"] is None
    assert "REAL_BROKER_ORDER_SUBMIT_ENABLED is not true" in result["block_reasons"]
    assert result["go_live_allowed"] is False


def test_live_order_submit_uses_adapter_after_all_manual_gates(monkeypatch, tmp_path) -> None:
    from institutional_trading_platform import web_app

    _enable_live_env(monkeypatch, tmp_path)
    monkeypatch.setenv("REAL_BROKER_ORDER_SUBMIT_ENABLED", "true")
    monkeypatch.setattr(web_app, "_LIVE_KILL_SWITCH_ENABLED", False)
    monkeypatch.setattr(web_app, "_market_hours_valid", lambda now=None: True)
    fake = _FakeKiteClient()
    monkeypatch.setattr(web_app, "_kite_client_from_env", lambda: fake)
    preview = web_app._live_order_preview({"symbol": "RELIANCE", "exchange": "NSE", "side": "BUY", "quantity": 1, "order_type": "LIMIT", "price": 1.0, "product": "MIS"})

    result = web_app._live_order_submit({"preview_id": preview["preview_id"], "typed_confirmation": "CONFIRM_LIVE_ORDER", "approval_mode": True})

    assert result["status"] == "SUBMITTED"
    assert result["broker_order_id"] == "order-123"
    assert result["order_status_reconciliation"]["status"] == "OPEN"
    assert result["go_live_allowed"] is False
    assert fake.submitted is True


def test_live_kill_switch_blocks_future_readiness() -> None:
    from institutional_trading_platform.web_app import _enable_live_kill_switch, _live_readiness

    result = _enable_live_kill_switch()
    readiness = _live_readiness()

    assert result["kill_switch_status"] == "ENABLED"
    assert result["go_live_allowed"] is False
    assert readiness["kill_switch_status"] == "ENABLED"
    assert readiness["go_live_allowed"] is False
