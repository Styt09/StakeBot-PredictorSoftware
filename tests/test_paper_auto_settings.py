from institutional_trading_platform.web_app import (
    HTML,
    _LAST_QUOTES,
    _PAPER,
    _paper_order,
    _paper_reset,
    _paper_settings_response,
    _paper_settings_update,
    _paper_auto_trade_plan,
    _paper_auto_trade_from_signal,
)


def setup_function() -> None:
    _paper_reset({"starting_balance": 100000})
    _LAST_QUOTES.clear()


def _quote(symbol: str = "RELIANCE", ltp: float = 100.0) -> None:
    _LAST_QUOTES[symbol] = {"symbol": symbol, "ltp": ltp, "validation_status": "VALIDATED", "data_source": "TEST_QUOTE"}


def _signal(symbol: str = "RELIANCE") -> dict:
    return {"symbol": symbol, "decision": "BUY", "validation_status": "VALIDATED", "confidence_score": 80, "risk_reward": 2}


def test_settings_ui_is_present() -> None:
    assert "Paper Auto Settings" in HTML
    assert "FIXED_QUANTITY" in HTML
    assert "FIXED_AMOUNT" in HTML
    assert "POINTS" in HTML
    assert "PERCENT" in HTML
    assert "/api/paper/settings" in HTML


def test_default_settings_exist() -> None:
    settings = _paper_settings_response()["settings"]
    assert settings["paper_auto_trade_enabled"] is False
    assert settings["sizing_mode"] == "FIXED_QUANTITY"
    assert settings["fixed_quantity"] == 1
    assert settings["fixed_amount"] == 1000.0
    assert settings["target_mode"] == "PERCENT"
    assert settings["target_value"] == 1.0
    assert settings["stop_loss_mode"] == "PERCENT"
    assert settings["stop_loss_value"] == 0.5
    assert settings["go_live_allowed"] is False


def test_fixed_quantity_update() -> None:
    result = _paper_settings_update({"sizing_mode": "FIXED_QUANTITY", "fixed_quantity": 7})
    assert result["settings"]["fixed_quantity"] == 7


def test_fixed_amount_update_and_quantity_calc() -> None:
    _quote(ltp=500)
    _paper_settings_update({"paper_auto_trade_enabled": True, "sizing_mode": "FIXED_AMOUNT", "fixed_amount": 2400})
    plan = _paper_auto_trade_plan("RELIANCE", _signal())
    assert plan["calculated_quantity"] == 4


def test_small_amount_blocks() -> None:
    _quote(ltp=500)
    _paper_settings_update({"paper_auto_trade_enabled": True, "sizing_mode": "FIXED_AMOUNT", "fixed_amount": 100})
    plan = _paper_auto_trade_plan("RELIANCE", _signal())
    assert "INSUFFICIENT_PAPER_AMOUNT" in plan["block_reasons"]


def test_max_open_positions_blocks() -> None:
    _quote(ltp=100)
    _paper_settings_update({"paper_auto_trade_enabled": True, "max_open_positions": 1})
    _paper_order({"symbol": "RELIANCE", "side": "BUY", "quantity": 1, "entry_price": 100})
    plan = _paper_auto_trade_plan("RELIANCE", _signal())
    assert "MAX_OPEN_POSITIONS_REACHED" in plan["block_reasons"]


def test_percent_target_stop_generation() -> None:
    _quote(ltp=100)
    _paper_settings_update({"paper_auto_trade_enabled": True, "target_mode": "PERCENT", "target_value": 1, "stop_loss_mode": "PERCENT", "stop_loss_value": 0.5})
    plan = _paper_auto_trade_plan("RELIANCE", _signal())
    assert plan["generated_target_1"] == 101
    assert plan["generated_target_2"] == 102
    assert plan["generated_stop_loss"] == 99.5


def test_points_target_stop_generation() -> None:
    _quote(ltp=100)
    _paper_settings_update({"paper_auto_trade_enabled": True, "target_mode": "POINTS", "target_value": 10, "stop_loss_mode": "POINTS", "stop_loss_value": 5})
    plan = _paper_auto_trade_plan("RELIANCE", _signal())
    assert plan["generated_target_1"] == 110
    assert plan["generated_target_2"] == 120
    assert plan["generated_stop_loss"] == 95


def test_armed_signal_opens_virtual_position_only() -> None:
    _quote(ltp=100)
    _paper_settings_update({"paper_auto_trade_enabled": True, "sizing_mode": "FIXED_QUANTITY", "fixed_quantity": 2})
    _paper_auto_trade_from_signal(_signal())
    assert len(_PAPER["open_positions"]) == 1
    assert _PAPER["open_positions"][0]["quantity"] == 2
    assert _PAPER["open_positions"][0]["go_live_allowed"] is False
