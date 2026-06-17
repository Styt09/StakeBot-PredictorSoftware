from institutional_trading_platform.terminal_page import TERMINAL_HTML
from institutional_trading_platform.web_app import _live_order_submit, _market_symbols, _paper_auto_trade_plan, _paper_settings_update


def test_terminal_html_contract() -> None:
    assert "Search Stock / Index" in TERMINAL_HTML
    assert "Use Signal in Paper Order" in TERMINAL_HTML
    assert "Quantity mode" in TERMINAL_HTML
    assert "Amount mode" in TERMINAL_HTML
    assert "PAPER MODE" in TERMINAL_HTML
    assert "REAL ORDERS DISABLED" in TERMINAL_HTML


def test_market_symbols_rel_is_limited() -> None:
    payload = _market_symbols("REL")
    assert payload["go_live_allowed"] is False
    assert len(payload["symbols"]) <= 50
    assert "RELIANCE" in payload["symbols"]


def test_paper_auto_on_weak_signal_is_blocked() -> None:
    _paper_settings_update({"paper_auto_trade_enabled": True})
    weak_signal = {
        "symbol": "RELIANCE",
        "decision": "NO_TRADE",
        "validation_status": "VALIDATED",
        "confidence_score": 20,
        "risk_reward": 0,
    }
    plan = _paper_auto_trade_plan("RELIANCE", weak_signal)
    assert plan["requested"] is True
    assert plan["state"] == "BLOCKED"
    assert plan["go_live_allowed"] is False


def test_real_live_order_submit_remains_fail_closed() -> None:
    result = _live_order_submit({"preview_id": "missing", "typed_confirmation": "CONFIRM_LIVE_ORDER", "approval_mode": True})
    assert result["status"] == "BLOCKED"
    assert result["broker_order_id"] is None
    assert result["go_live_allowed"] is False
