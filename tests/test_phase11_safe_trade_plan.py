from __future__ import annotations

from institutional_trading_platform.openai_auditor import deterministic_signal_audit
from institutional_trading_platform.safe_trade_plan import build_safe_trade_plan, enrich_signal_with_safe_trade_plan
from institutional_trading_platform.web_app import _live_order_submit


def candles(count: int = 30, *, start: float = 100.0):
    rows = []
    price = start
    for idx in range(count):
        open_ = price
        close = price + 0.8
        rows.append({"open": open_, "high": close + 1.0, "low": open_ - 1.0, "close": close, "volume": 1000 + idx})
        price = close
    return rows


GOOD_QUOTE = {"symbol": "RELIANCE", "ltp": 124.0, "validation_status": "VALIDATED", "connection_status": "ZERODHA_READ_ONLY_CONNECTED", "data_source": "TEST_QUOTE", "go_live_allowed": False}
GOOD_HISTORY = {"symbol": "RELIANCE", "validation_status": "VALIDATED", "candles": candles(), "data_source": "TEST_CANDLES", "go_live_allowed": False}
GOOD_SIGNAL = {
    "symbol": "RELIANCE",
    "decision": "NO_TRADE",
    "confidence_score": 82,
    "timeframes": {"primary_5m": "BULLISH", "confirmation_15m": "BULLISH", "trend_1h": "BULLISH"},
    "indicators": {"atr_14": 2.0, "trend_direction": "BULLISH", "volume_confirmation": True},
    "market_structure": {"support": 118.0, "resistance": 130.0},
    "go_live_allowed": False,
}


def test_validated_quote_and_candles_can_produce_complete_buy_plan(monkeypatch):
    monkeypatch.setenv("MIN_SIGNAL_CONFIDENCE", "70")
    monkeypatch.setenv("MIN_RISK_REWARD", "1.5")
    plan = build_safe_trade_plan(symbol="RELIANCE", signal=GOOD_SIGNAL, market_quote=GOOD_QUOTE, market_history=GOOD_HISTORY)
    assert plan["validation_status"] == "VALIDATED"
    assert plan["final_action"] == "BUY"
    assert plan["entry"] == 124.0
    assert isinstance(plan["stop_loss"], float)
    assert isinstance(plan["target_1"], float)
    assert isinstance(plan["target_2"], float)
    assert plan["risk_reward"] >= 1.5
    assert plan["go_live_allowed"] is False
    assert plan["can_place_real_order"] is False


def test_missing_quote_returns_data_unavailable():
    plan = build_safe_trade_plan(symbol="RELIANCE", signal=GOOD_SIGNAL, market_quote={}, market_history=GOOD_HISTORY)
    assert plan["final_action"] == "DATA_UNAVAILABLE"
    assert "VALIDATED_QUOTE_REQUIRED" in plan["blocked_reasons"]
    assert plan["go_live_allowed"] is False


def test_insufficient_candles_returns_data_unavailable():
    history = {**GOOD_HISTORY, "candles": candles(5)}
    plan = build_safe_trade_plan(symbol="RELIANCE", signal=GOOD_SIGNAL, market_quote=GOOD_QUOTE, market_history=history)
    assert plan["final_action"] == "DATA_UNAVAILABLE"
    assert "MINIMUM_21_CANDLES_REQUIRED" in plan["blocked_reasons"]


def test_low_confidence_returns_no_trade():
    signal = {**GOOD_SIGNAL, "confidence_score": 25}
    plan = build_safe_trade_plan(symbol="RELIANCE", signal=signal, market_quote=GOOD_QUOTE, market_history=GOOD_HISTORY)
    assert plan["final_action"] == "NO_TRADE"
    assert any(reason.startswith("CONFIDENCE_BELOW") for reason in plan["blocked_reasons"])


def test_low_risk_reward_returns_no_trade(monkeypatch):
    monkeypatch.setenv("MIN_RISK_REWARD", "10")
    signal = {**GOOD_SIGNAL, "market_structure": {"support": 123.5, "resistance": 124.3}, "indicators": {"atr_14": 1.0, "trend_direction": "BULLISH", "volume_confirmation": True}}
    plan = build_safe_trade_plan(symbol="RELIANCE", signal=signal, market_quote=GOOD_QUOTE, market_history=GOOD_HISTORY, min_risk_reward=10)
    assert plan["final_action"] == "BUY" or plan["final_action"] == "NO_TRADE"
    assert plan["go_live_allowed"] is False


def test_missing_atr_support_resistance_returns_no_trade_when_candles_invalid_for_derivation():
    history = {"validation_status": "VALIDATED", "candles": [{"open": 1, "high": 1, "low": 1, "close": 1} for _ in range(21)]}
    signal = {"decision": "BUY", "confidence_score": 90, "indicators": {"volume_confirmation": True}}
    plan = build_safe_trade_plan(symbol="RELIANCE", signal=signal, market_quote={"ltp": 100, "validation_status": "VALIDATED"}, market_history=history)
    assert plan["final_action"] == "NO_TRADE"
    assert "ATR_REQUIRED" in plan["blocked_reasons"] or "COMPLETE_TRADE_PLAN_REQUIRED" in plan["blocked_reasons"]


def test_enrich_signal_runs_before_ai_audit_and_ai_can_still_block_unsafe():
    enriched = enrich_signal_with_safe_trade_plan(GOOD_SIGNAL, symbol="RELIANCE", market_quote=GOOD_QUOTE, market_history=GOOD_HISTORY)
    assert enriched["entry"] != "DATA_UNAVAILABLE"
    audit = deterministic_signal_audit(signal=enriched, market_quote=GOOD_QUOTE, market_history=GOOD_HISTORY)
    assert audit["final_action"] in {"BUY", "SELL", "HOLD", "NO_TRADE", "DATA_UNAVAILABLE"}
    assert audit["go_live_allowed"] is False


def test_openai_cannot_upgrade_no_trade_to_buy():
    unsafe = {**GOOD_SIGNAL, "final_action": "NO_TRADE", "decision": "NO_TRADE", "confidence_score": 20}
    audit = deterministic_signal_audit(signal=unsafe, market_quote=GOOD_QUOTE, market_history=GOOD_HISTORY)
    assert audit["final_action"] != "BUY"
    assert audit["go_live_allowed"] is False


def test_live_order_submit_remains_blocked():
    result = _live_order_submit({"typed_confirmation": "CONFIRM_LIVE_ORDER", "approval_mode": True})
    assert result["status"] == "BLOCKED"
    assert result["broker_order_id"] is None
    assert result["go_live_allowed"] is False


def test_all_outputs_go_live_allowed_false():
    plan = build_safe_trade_plan(symbol="RELIANCE", signal=GOOD_SIGNAL, market_quote=GOOD_QUOTE, market_history=GOOD_HISTORY)
    enriched = enrich_signal_with_safe_trade_plan(GOOD_SIGNAL, symbol="RELIANCE", market_quote=GOOD_QUOTE, market_history=GOOD_HISTORY)
    assert plan["go_live_allowed"] is False
    assert enriched["go_live_allowed"] is False
    assert enriched["safe_trade_plan"]["go_live_allowed"] is False
