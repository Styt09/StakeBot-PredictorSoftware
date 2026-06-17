from institutional_trading_platform.web_app import (
    HTML,
    _PAPER,
    _LAST_QUOTES,
    _live_order_submit,
    _market_quote,
    _paper_balance_add,
    _paper_order,
    _paper_position_close,
    _paper_reset,
    _paper_statement,
    _paper_status,
    _paper_auto_trade_toggle,
)


def setup_function() -> None:
    _paper_reset({"starting_balance": 100000})
    _LAST_QUOTES.clear()


def test_paper_ui_contract_is_present() -> None:
    assert "Paper Trading Terminal" in HTML
    assert "PAPER MODE" in HTML
    assert "Virtual paper money only" in HTML
    assert "REAL ORDERS DISABLED" in HTML
    assert "/api/paper/status" in HTML
    assert "/api/paper/order" in HTML
    assert "/api/paper/balance/add" in HTML
    assert "/api/paper/reset" in HTML
    assert "/api/paper/position/close" in HTML
    assert "/api/paper/auto-trade/toggle" in HTML


def test_paper_status_returns_default_virtual_account() -> None:
    payload = _paper_status()

    assert payload["account_summary"]["mode"] == "PAPER_TRADING_ONLY"
    assert payload["account_summary"]["cash_balance"] == 100000
    assert payload["account_summary"]["equity"] == 100000
    assert payload["account_summary"]["win_rate"] == "DATA_UNAVAILABLE"
    assert payload["go_live_allowed"] is False


def test_add_balance_increases_cash_balance() -> None:
    result = _paper_balance_add({"amount": 5000})

    assert result["status"] == "PASS"
    assert result["paper_status"]["account_summary"]["cash_balance"] == 105000
    assert result["paper_status"]["go_live_allowed"] is False


def test_reset_clears_positions_and_statement() -> None:
    _paper_order({"symbol": "RELIANCE", "side": "BUY", "quantity": 1, "entry_price": 100, "stop_loss": 95, "target_1": 110, "target_2": 120})
    reset = _paper_reset({"starting_balance": 50000})

    assert reset["status"] == "PASS"
    assert reset["paper_status"]["account_summary"]["cash_balance"] == 50000
    assert reset["paper_status"]["open_positions"] == ()


def test_manual_paper_buy_creates_open_position_without_real_broker_call() -> None:
    result = _paper_order({"symbol": "RELIANCE", "side": "BUY", "quantity": 2, "entry_price": 100, "stop_loss": 95, "target_1": 110, "target_2": 120})

    assert result["status"] == "PASS"
    assert result["paper_order"]["symbol"] == "RELIANCE"
    assert result["paper_order"]["status"] == "OPEN"
    assert result["go_live_allowed"] is False


def test_manual_paper_sell_closes_existing_long_position() -> None:
    _paper_order({"symbol": "RELIANCE", "side": "BUY", "quantity": 1, "entry_price": 100, "stop_loss": 95, "target_1": 110, "target_2": 120})
    result = _paper_order({"symbol": "RELIANCE", "side": "SELL", "quantity": 1, "entry_price": 105})

    assert result["status"] == "PASS"
    assert result["closed_trade"]["exit_reason"] == "MANUAL_EXIT"
    assert result["closed_trade"]["pnl"] == 5
    assert result["go_live_allowed"] is False


def test_target_hit_closes_position_and_records_profit() -> None:
    _paper_order({"symbol": "RELIANCE", "side": "BUY", "quantity": 1, "entry_price": 100, "stop_loss": 95, "target_1": 105, "target_2": 110})
    _LAST_QUOTES["RELIANCE"] = {"symbol": "RELIANCE", "ltp": 106, "validation_status": "VALIDATED", "data_source": "TEST_QUOTE"}
    _market_quote("RELIANCE")
    # If live quote is unavailable in tests, directly close via refreshed status path.
    from institutional_trading_platform.web_app import _paper_evaluate_positions
    _paper_evaluate_positions("RELIANCE", 106, "TEST_QUOTE")
    statement = _paper_statement()

    assert statement["closed_trades"][-1]["exit_reason"] == "TARGET_1_HIT"
    assert statement["closed_trades"][-1]["pnl"] == 6


def test_stop_loss_hit_closes_position_and_records_loss() -> None:
    _paper_order({"symbol": "RELIANCE", "side": "BUY", "quantity": 1, "entry_price": 100, "stop_loss": 95, "target_1": 105, "target_2": 110})
    from institutional_trading_platform.web_app import _paper_evaluate_positions
    _paper_evaluate_positions("RELIANCE", 94, "TEST_QUOTE")
    statement = _paper_statement()

    assert statement["closed_trades"][-1]["exit_reason"] == "STOP_LOSS_HIT"
    assert statement["closed_trades"][-1]["pnl"] == -6


def test_statement_records_closed_trades() -> None:
    _paper_order({"symbol": "RELIANCE", "side": "BUY", "quantity": 1, "entry_price": 100})
    _paper_order({"symbol": "RELIANCE", "side": "SELL", "quantity": 1, "entry_price": 101})
    statement = _paper_statement()

    assert statement["closed_trades"]
    assert statement["ledger_entries"]
    assert statement["go_live_allowed"] is False


def test_paper_auto_trade_is_off_by_default() -> None:
    payload = _paper_status()

    assert payload["account_summary"]["paper_auto_trade_state"] == "OFF"
    assert _PAPER["paper_auto_trade_enabled"] is False


def test_paper_auto_trade_toggle_never_places_real_orders() -> None:
    result = _paper_auto_trade_toggle({"enabled": True})
    live = _live_order_submit({"preview_id": "missing", "typed_confirmation": "CONFIRM_LIVE_ORDER", "approval_mode": True})

    assert result["status"] == "PASS"
    assert result["go_live_allowed"] is False
    assert live["status"] == "BLOCKED"
    assert live["broker_order_id"] is None
    assert live["go_live_allowed"] is False
