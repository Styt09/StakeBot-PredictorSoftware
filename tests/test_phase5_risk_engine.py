from institutional_trading_platform.risk_engine import RiskEngine, RiskInput
from institutional_trading_platform.safe_config import getTradingConfig
from institutional_trading_platform.web_app import _live_order_submit


GOOD_HEALTH = {
    "state": "CONNECTED",
    "missingData": False,
    "marketOpen": True,
    "blockedReasons": (),
}

STALE_HEALTH = {
    "state": "STALE",
    "missingData": False,
    "marketOpen": True,
    "blockedReasons": ("MARKET_DATA_STALE",),
}

GOOD_SIGNAL = {
    "symbol": "RELIANCE",
    "action": "BUY",
    "entry": 100.0,
    "stop_loss": 98.0,
    "targets": (104.0,),
    "confidence": 80.0,
    "risk_reward": 2.0,
    "go_live_allowed": False,
}


def _risk(**overrides):
    payload = {
        "symbol": "RELIANCE",
        "side": "BUY",
        "quantity": 1,
        "signal": GOOD_SIGNAL,
        "market_health": GOOD_HEALTH,
        "account_state": {"realized_pnl": 0},
        "open_positions": (),
        "order_path": "PAPER",
        "kill_switch_active": False,
    }
    payload.update(overrides)
    return payload


def test_risk_engine_blocks_read_only_order() -> None:
    engine = RiskEngine(getTradingConfig({"TRADING_MODE": "READ_ONLY"}))
    result = engine.evaluate(RiskInput(**_risk()))
    assert result["allowed"] is False
    assert "TRADING_MODE_READ_ONLY" in result["blocked_reasons"]
    assert result["go_live_allowed"] is False


def test_risk_engine_allows_safe_paper_order() -> None:
    engine = RiskEngine(getTradingConfig({"TRADING_MODE": "PAPER", "MAX_QTY_PER_ORDER": "2"}))
    result = engine.evaluate(RiskInput(**_risk()))
    assert result["allowed"] is True
    assert result["blocked_reasons"] == ()
    assert result["go_live_allowed"] is False


def test_risk_engine_blocks_missing_stop_loss() -> None:
    signal = dict(GOOD_SIGNAL, stop_loss=None)
    result = RiskEngine().evaluate(RiskInput(**_risk(signal=signal)))
    assert result["allowed"] is False
    assert "STOP_LOSS_REQUIRED" in result["blocked_reasons"]


def test_risk_engine_blocks_missing_target() -> None:
    signal = dict(GOOD_SIGNAL, targets=())
    result = RiskEngine().evaluate(RiskInput(**_risk(signal=signal)))
    assert result["allowed"] is False
    assert "TARGET_REQUIRED" in result["blocked_reasons"]


def test_risk_engine_blocks_low_confidence() -> None:
    signal = dict(GOOD_SIGNAL, confidence=40)
    result = RiskEngine().evaluate(RiskInput(**_risk(signal=signal)))
    assert result["allowed"] is False
    assert "SIGNAL_CONFIDENCE_BELOW_MINIMUM" in result["blocked_reasons"]


def test_risk_engine_blocks_stale_data() -> None:
    result = RiskEngine().evaluate(RiskInput(**_risk(market_health=STALE_HEALTH)))
    assert result["allowed"] is False
    assert "MARKET_DATA_NOT_ACTIONABLE" in result["blocked_reasons"]


def test_risk_engine_blocks_quantity_above_max() -> None:
    engine = RiskEngine(getTradingConfig({"TRADING_MODE": "PAPER", "MAX_QTY_PER_ORDER": "1"}))
    result = engine.evaluate(RiskInput(**_risk(quantity=2)))
    assert result["allowed"] is False
    assert "MAX_QTY_PER_ORDER_EXCEEDED" in result["blocked_reasons"]


def test_risk_engine_blocks_duplicate_order() -> None:
    result = RiskEngine().evaluate(RiskInput(**_risk(open_positions=({"symbol": "RELIANCE", "side": "LONG"},))))
    assert result["allowed"] is False
    assert "DUPLICATE_ORDER_OR_POSITION" in result["blocked_reasons"]


def test_risk_engine_blocks_kill_switch_active() -> None:
    result = RiskEngine().evaluate(RiskInput(**_risk(kill_switch_active=True)))
    assert result["allowed"] is False
    assert "KILL_SWITCH_ACTIVE" in result["blocked_reasons"]


def test_live_order_submit_remains_blocked() -> None:
    result = _live_order_submit({"preview_id": "missing", "typed_confirmation": "CONFIRM_LIVE_ORDER", "approval_mode": True})
    assert result["status"] == "BLOCKED"
    assert result["broker_order_id"] is None
    assert result["go_live_allowed"] is False
