from institutional_trading_platform.shadow_trading import ShadowTradingEngine, ShadowTradingState, ShadowOrderStatus
from institutional_trading_platform.web_app import _live_order_submit


GOOD_QUOTE = {"symbol": "RELIANCE", "ltp": 100.0, "validation_status": "VALIDATED", "go_live_allowed": False}
BAD_QUOTE = {"symbol": "RELIANCE", "ltp": "DATA_UNAVAILABLE", "validation_status": "DATA_UNAVAILABLE", "go_live_allowed": False}
GOOD_SIGNAL = {"symbol": "RELIANCE", "action": "BUY", "confidence": 80.0, "go_live_allowed": False}
NO_TRADE_SIGNAL = {"symbol": "RELIANCE", "action": "NO_TRADE", "confidence": 20.0, "go_live_allowed": False}
GOOD_RISK = {"allowed": True, "blocked_reasons": (), "go_live_allowed": False}
BAD_RISK = {"allowed": False, "blocked_reasons": ("MARKET_DATA_NOT_ACTIONABLE",), "go_live_allowed": False}


def test_shadow_buy_creates_theoretical_order_after_risk_approval() -> None:
    engine = ShadowTradingEngine(ShadowTradingState())
    result = engine.evaluate_order(symbol="RELIANCE", side="BUY", quantity=1, quote=GOOD_QUOTE, safe_signal=GOOD_SIGNAL, risk=GOOD_RISK)
    assert result["status"] == "PASS"
    assert result["shadow_order"]["status"] == ShadowOrderStatus.SHADOW_FILLED_THEORETICAL.value
    assert len(engine.state.open_positions) == 1
    assert result["go_live_allowed"] is False


def test_shadow_buy_blocked_when_risk_fails() -> None:
    engine = ShadowTradingEngine(ShadowTradingState())
    result = engine.evaluate_order(symbol="RELIANCE", side="BUY", quantity=1, quote=GOOD_QUOTE, safe_signal=GOOD_SIGNAL, risk=BAD_RISK)
    assert result["status"] == "SHADOW_BLOCKED"
    assert "MARKET_DATA_NOT_ACTIONABLE" in result["blocked_reasons"]
    assert engine.state.open_positions == []


def test_shadow_buy_blocked_when_market_data_missing() -> None:
    engine = ShadowTradingEngine(ShadowTradingState())
    result = engine.evaluate_order(symbol="RELIANCE", side="BUY", quantity=1, quote=BAD_QUOTE, safe_signal=GOOD_SIGNAL, risk=GOOD_RISK)
    assert result["status"] == "SHADOW_BLOCKED"
    assert result["reason"] == "VALIDATED_QUOTE_REQUIRED"


def test_shadow_buy_blocked_when_signal_no_trade() -> None:
    engine = ShadowTradingEngine(ShadowTradingState())
    result = engine.evaluate_order(symbol="RELIANCE", side="BUY", quantity=1, quote=GOOD_QUOTE, safe_signal=NO_TRADE_SIGNAL, risk=GOOD_RISK)
    assert result["status"] == "SHADOW_BLOCKED"
    assert result["reason"] == "SHADOW_SIGNAL_NOT_ACTIONABLE"


def test_shadow_sell_closes_theoretical_long_position() -> None:
    engine = ShadowTradingEngine(ShadowTradingState())
    engine.evaluate_order(symbol="RELIANCE", side="BUY", quantity=2, quote=GOOD_QUOTE, safe_signal=GOOD_SIGNAL, risk=GOOD_RISK)
    sell_quote = {"symbol": "RELIANCE", "ltp": 105.0, "validation_status": "VALIDATED"}
    sell_signal = {"symbol": "RELIANCE", "action": "SELL", "confidence": 80.0, "go_live_allowed": False}
    result = engine.evaluate_order(symbol="RELIANCE", side="SELL", quantity=2, quote=sell_quote, safe_signal=sell_signal, risk=GOOD_RISK)
    assert result["status"] == "PASS"
    assert len(engine.state.open_positions) == 0
    assert len(engine.state.closed_trades) == 1
    assert engine.state.closed_trades[0]["pnl"] == 10.0


def test_shadow_sell_blocked_when_no_position_exists() -> None:
    engine = ShadowTradingEngine(ShadowTradingState())
    sell_signal = {"symbol": "RELIANCE", "action": "SELL", "confidence": 80.0, "go_live_allowed": False}
    result = engine.evaluate_order(symbol="RELIANCE", side="SELL", quantity=1, quote=GOOD_QUOTE, safe_signal=sell_signal, risk=GOOD_RISK)
    assert result["status"] == "SHADOW_BLOCKED"
    assert result["reason"] == "NO_OPEN_SHADOW_LONG_POSITION"


def test_shadow_pnl_updates_mark_to_market() -> None:
    engine = ShadowTradingEngine(ShadowTradingState())
    engine.evaluate_order(symbol="RELIANCE", side="BUY", quantity=2, quote=GOOD_QUOTE, safe_signal=GOOD_SIGNAL, risk=GOOD_RISK)
    engine.mark_to_market({"RELIANCE": {"ltp": 103.0}})
    assert engine.state.unrealized_pnl == 6.0


def test_shadow_audit_log_records_create_fill_block_reset() -> None:
    engine = ShadowTradingEngine(ShadowTradingState())
    engine.evaluate_order(symbol="RELIANCE", side="BUY", quantity=1, quote=GOOD_QUOTE, safe_signal=GOOD_SIGNAL, risk=BAD_RISK)
    engine.reset()
    events = [row["event"] for row in engine.state.audit_log]
    assert "SHADOW_ORDER_CREATED" in events
    assert "SHADOW_ORDER_BLOCKED" in events
    assert "SHADOW_RESET" in events


def test_shadow_report_returns_required_fields() -> None:
    engine = ShadowTradingEngine(ShadowTradingState())
    report = engine.report()
    assert report["go_live_allowed"] is False
    assert "orders" in report
    assert "trades" in report
    assert "open_positions" in report
    assert "audit_log" in report
    assert "drift_placeholder" in report
    assert "accuracy_report_placeholder" in report


def test_real_live_order_submit_remains_blocked() -> None:
    result = _live_order_submit({"preview_id": "missing", "typed_confirmation": "CONFIRM_LIVE_ORDER", "approval_mode": True})
    assert result["status"] == "BLOCKED"
    assert result["broker_order_id"] is None
    assert result["go_live_allowed"] is False
