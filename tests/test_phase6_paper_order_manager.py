from institutional_trading_platform.paper_order_manager import PaperOrderManager, PaperExecutionState, PaperOrderStatus
from institutional_trading_platform.web_app import _live_order_submit


GOOD_QUOTE = {"symbol": "RELIANCE", "ltp": 100.0, "validation_status": "VALIDATED", "go_live_allowed": False}
GOOD_RISK = {"allowed": True, "blocked_reasons": (), "go_live_allowed": False}
BAD_RISK = {"allowed": False, "blocked_reasons": ("MARKET_DATA_NOT_ACTIONABLE",), "go_live_allowed": False}


def test_paper_buy_creates_order_after_risk_approval() -> None:
    manager = PaperOrderManager(PaperExecutionState(cash_balance=1000.0))
    result = manager.create_order(symbol="RELIANCE", side="BUY", quantity=1, quote=GOOD_QUOTE, risk=GOOD_RISK, stop_loss=98.0, target_1=104.0)
    assert result["status"] == "PASS"
    assert result["paper_order"]["status"] == PaperOrderStatus.PAPER_FILLED.value
    assert len(manager.state.open_positions) == 1
    assert manager.state.cash_balance == 900.0
    assert result["go_live_allowed"] is False


def test_paper_buy_blocked_when_risk_fails() -> None:
    manager = PaperOrderManager(PaperExecutionState())
    result = manager.create_order(symbol="RELIANCE", side="BUY", quantity=1, quote=GOOD_QUOTE, risk=BAD_RISK)
    assert result["status"] == "BLOCKED"
    assert "MARKET_DATA_NOT_ACTIONABLE" in result["blocked_reasons"]
    assert manager.state.open_positions == []


def test_paper_buy_blocked_when_market_data_missing() -> None:
    manager = PaperOrderManager(PaperExecutionState())
    bad_quote = {"symbol": "RELIANCE", "ltp": "DATA_UNAVAILABLE", "validation_status": "DATA_UNAVAILABLE"}
    result = manager.create_order(symbol="RELIANCE", side="BUY", quantity=1, quote=bad_quote, risk=GOOD_RISK)
    assert result["status"] == "BLOCKED"
    assert result["reason"] == "VALIDATED_QUOTE_REQUIRED"


def test_paper_buy_blocked_when_quantity_invalid() -> None:
    manager = PaperOrderManager(PaperExecutionState())
    result = manager.create_order(symbol="RELIANCE", side="BUY", quantity=0, quote=GOOD_QUOTE, risk=GOOD_RISK)
    assert result["status"] == "BLOCKED"
    assert result["reason"] == "QUANTITY_REQUIRED"


def test_paper_sell_closes_existing_long_position() -> None:
    manager = PaperOrderManager(PaperExecutionState(cash_balance=1000.0))
    manager.create_order(symbol="RELIANCE", side="BUY", quantity=1, quote=GOOD_QUOTE, risk=GOOD_RISK)
    sell_quote = {"symbol": "RELIANCE", "ltp": 105.0, "validation_status": "VALIDATED"}
    result = manager.create_order(symbol="RELIANCE", side="SELL", quantity=1, quote=sell_quote, risk=GOOD_RISK)
    assert result["status"] == "PASS"
    assert len(manager.state.open_positions) == 0
    assert len(manager.state.closed_trades) == 1
    assert manager.state.closed_trades[0]["pnl"] == 5.0


def test_paper_sell_blocked_when_no_position_exists() -> None:
    manager = PaperOrderManager(PaperExecutionState())
    result = manager.create_order(symbol="RELIANCE", side="SELL", quantity=1, quote=GOOD_QUOTE, risk=GOOD_RISK)
    assert result["status"] == "BLOCKED"
    assert result["reason"] == "NO_OPEN_LONG_POSITION"


def test_paper_pnl_updates_mark_to_market() -> None:
    manager = PaperOrderManager(PaperExecutionState(cash_balance=1000.0))
    manager.create_order(symbol="RELIANCE", side="BUY", quantity=2, quote=GOOD_QUOTE, risk=GOOD_RISK)
    manager.mark_to_market({"RELIANCE": {"ltp": 103.0}})
    assert manager.state.unrealized_pnl == 6.0


def test_paper_audit_log_records_events() -> None:
    manager = PaperOrderManager(PaperExecutionState())
    manager.create_order(symbol="RELIANCE", side="BUY", quantity=1, quote=GOOD_QUOTE, risk=BAD_RISK)
    events = [row["event"] for row in manager.state.audit_log]
    assert "PAPER_ORDER_CREATED" in events
    assert "PAPER_ORDER_BLOCKED" in events


def test_paper_cancel_works_for_unfilled_order() -> None:
    manager = PaperOrderManager(PaperExecutionState())
    result = manager.create_order(symbol="RELIANCE", side="BUY", quantity=1, quote=GOOD_QUOTE, risk=BAD_RISK)
    order_id = result["paper_order"]["order_id"]
    cancel = manager.cancel_order(order_id)
    assert cancel["status"] == "PASS"
    assert cancel["order"]["status"] == PaperOrderStatus.CANCELLED.value


def test_report_and_status_shapes_are_safe() -> None:
    manager = PaperOrderManager(PaperExecutionState())
    status = manager.status()
    report = manager.report()
    assert status["go_live_allowed"] is False
    assert report["go_live_allowed"] is False
    assert "orders" in report
    assert "audit_log" in report


def test_live_order_submit_remains_blocked() -> None:
    result = _live_order_submit({"preview_id": "missing", "typed_confirmation": "CONFIRM_LIVE_ORDER", "approval_mode": True})
    assert result["status"] == "BLOCKED"
    assert result["broker_order_id"] is None
    assert result["go_live_allowed"] is False
