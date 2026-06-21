from institutional_trading_platform.quant_trader_style_adapter import DATA_UNAVAILABLE, QuantTraderStyleAdapter


def _history(direction="up", n=40):
    price = 100.0
    candles = []
    for i in range(n):
        price += 0.5 if direction == "up" else -0.5
        candles.append({"timestamp": str(i), "open": price - 0.1, "high": price + 0.4, "low": price - 0.4, "close": price, "volume": 1000})
    return {"validation_status": "VALIDATED", "candles": tuple(candles)}


def test_bullish_target_position_is_long_and_safe():
    histories = {"1m": _history("up"), "5m": _history("up"), "15m": _history("up"), "60m": _history("up")}
    out = QuantTraderStyleAdapter().evaluate("RELIANCE", histories)
    assert out["decision"] == "BUY"
    assert out["target_position"] == 1
    assert out["execution_status"] == "PAPER_SHADOW_ONLY_REAL_ORDER_DISABLED"
    assert out["go_live_allowed"] is False


def test_bearish_target_position_is_short_instruction_only():
    histories = {"1m": _history("down"), "5m": _history("down"), "15m": _history("down"), "60m": _history("down")}
    out = QuantTraderStyleAdapter().evaluate("RELIANCE", histories)
    assert out["decision"] == "SELL"
    assert out["target_position"] == -1
    assert out["execution_status"] == "PAPER_SHADOW_ONLY_REAL_ORDER_DISABLED"
    assert out["go_live_allowed"] is False


def test_missing_timeframes_fail_closed():
    out = QuantTraderStyleAdapter().evaluate("RELIANCE", {"1m": _history("up")})
    assert out["decision"] == DATA_UNAVAILABLE
    assert out["target_position"] == 0
    assert out["go_live_allowed"] is False
    assert "MISSING_OR_INSUFFICIENT_TIMEFRAMES" in out["reasons"][0]
