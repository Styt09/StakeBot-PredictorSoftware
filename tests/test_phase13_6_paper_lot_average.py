from __future__ import annotations

from institutional_trading_platform import web_app


def setup_function() -> None:
    web_app._paper_reset({"starting_balance": 100000})


def test_paper_buy_adds_lot_and_recalculates_average_price() -> None:
    first = web_app._paper_order({"symbol": "RELIANCE", "side": "BUY", "quantity": 10, "entry_price": 100})
    second = web_app._paper_order({"symbol": "RELIANCE", "side": "BUY", "quantity": 5, "entry_price": 90})

    assert first["status"] == "PASS"
    assert second["status"] == "PASS"
    status = web_app._paper_status()
    positions = status["open_positions"]
    assert len(positions) == 1
    position = positions[0]
    assert position["quantity"] == 15
    assert position["entry_price"] == 96.67
    assert position["lot_count"] == 2
    assert position["go_live_allowed"] is False


def test_paper_sell_partially_reduces_open_lot_position() -> None:
    web_app._paper_order({"symbol": "RELIANCE", "side": "BUY", "quantity": 10, "entry_price": 100})
    result = web_app._paper_order({"symbol": "RELIANCE", "side": "SELL", "quantity": 4, "entry_price": 110})

    assert result["status"] == "PASS"
    status = web_app._paper_status()
    assert status["open_positions"][0]["quantity"] == 6
    assert result["partial_trade"]["quantity"] == 4
    assert result["partial_trade"]["pnl"] == 40
    assert result["go_live_allowed"] is False


def test_auto_scale_in_defaults_to_off_for_safety() -> None:
    web_app._paper_settings_update({"paper_auto_trade_enabled": True, "fixed_quantity": 1})
    web_app._paper_order({"symbol": "RELIANCE", "side": "BUY", "quantity": 1, "entry_price": 100})
    web_app._LAST_QUOTES["RELIANCE"] = {"ltp": 99, "validation_status": "VALIDATED", "data_source": "TEST_QUOTE"}
    signal = {"symbol": "RELIANCE", "decision": "BUY", "validation_status": "VALIDATED", "confidence_score": 90, "risk_reward": 3}
    plan = web_app._paper_auto_trade_plan("RELIANCE", signal)
    assert "AUTO_SCALE_IN_OFF" in plan["block_reasons"]
    assert plan["go_live_allowed"] is False
