from datetime import datetime
from zoneinfo import ZoneInfo

from institutional_trading_platform.signal_safety import safe_signal_from_existing_signal
from institutional_trading_platform.web_app import _live_order_submit, _live_signal


GOOD_HEALTH = {
    "state": "CONNECTED",
    "missingData": False,
    "blockedReasons": (),
}

STALE_HEALTH = {
    "state": "STALE",
    "missingData": False,
    "blockedReasons": ("MARKET_DATA_STALE",),
}


def _signal(**overrides):
    payload = {
        "symbol": "RELIANCE",
        "decision": "BUY",
        "entry": 100.0,
        "stop_loss": 98.0,
        "target_1": 104.0,
        "target_2": 106.0,
        "confidence_score": 80,
        "risk_reward": 2.0,
        "signal_reasons": ("MULTI_TIMEFRAME_ALIGNED",),
        "timestamp": datetime(2026, 1, 5, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata")).isoformat(),
    }
    payload.update(overrides)
    return payload


def test_safe_signal_returns_required_fields() -> None:
    payload = safe_signal_from_existing_signal("RELIANCE", _signal(), GOOD_HEALTH, min_confidence=70)
    expected = {
        "symbol",
        "timeframe",
        "action",
        "entry",
        "stop_loss",
        "targets",
        "confidence",
        "confidence_grade",
        "expected_move_points",
        "risk_reward",
        "regime",
        "reasons",
        "blocked_reasons",
        "timestamp",
        "data_quality",
        "go_live_allowed",
    }
    assert expected.issubset(payload.keys())
    assert payload["action"] == "BUY"
    assert payload["go_live_allowed"] is False


def test_stale_data_returns_data_unavailable() -> None:
    payload = safe_signal_from_existing_signal("RELIANCE", _signal(), STALE_HEALTH, min_confidence=70)
    assert payload["action"] == "DATA_UNAVAILABLE"
    assert payload["data_quality"] == "STALE"
    assert "MARKET_DATA_STALE" in payload["blocked_reasons"]
    assert payload["go_live_allowed"] is False


def test_missing_stop_loss_blocks_buy_sell() -> None:
    payload = safe_signal_from_existing_signal("RELIANCE", _signal(stop_loss="DATA_UNAVAILABLE"), GOOD_HEALTH, min_confidence=70)
    assert payload["action"] == "NO_TRADE"
    assert "STOP_LOSS_REQUIRED" in payload["blocked_reasons"]


def test_missing_target_blocks_buy_sell() -> None:
    payload = safe_signal_from_existing_signal("RELIANCE", _signal(target_1="DATA_UNAVAILABLE", target_2="DATA_UNAVAILABLE"), GOOD_HEALTH, min_confidence=70)
    assert payload["action"] == "NO_TRADE"
    assert "TARGET_REQUIRED" in payload["blocked_reasons"]


def test_missing_risk_reward_blocks_buy_sell() -> None:
    payload = safe_signal_from_existing_signal("RELIANCE", _signal(risk_reward="DATA_UNAVAILABLE"), GOOD_HEALTH, min_confidence=70)
    assert payload["action"] == "NO_TRADE"
    assert "RISK_REWARD_REQUIRED" in payload["blocked_reasons"]


def test_low_confidence_returns_no_trade() -> None:
    payload = safe_signal_from_existing_signal("RELIANCE", _signal(confidence_score=40), GOOD_HEALTH, min_confidence=70)
    assert payload["action"] == "NO_TRADE"
    assert "CONFIDENCE_BELOW_MINIMUM" in payload["blocked_reasons"]


def test_existing_live_signal_still_returns_payload() -> None:
    payload = _live_signal("RELIANCE")
    assert payload["symbol"] == "RELIANCE"
    assert payload["go_live_allowed"] is False


def test_live_order_submit_remains_blocked() -> None:
    result = _live_order_submit({"preview_id": "missing", "typed_confirmation": "CONFIRM_LIVE_ORDER", "approval_mode": True})
    assert result["status"] == "BLOCKED"
    assert result["broker_order_id"] is None
    assert result["go_live_allowed"] is False
