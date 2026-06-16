"""Strict live signal engine for ALPHA-GATE X.

The engine never fabricates a BUY/SELL signal. Missing candles return
DATA_UNAVAILABLE. Weak or conflicting evidence returns NO_TRADE.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Mapping, Sequence

DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
NO_TRADE = "NO_TRADE"


def signal_unavailable(symbol: str, reason: str) -> dict[str, Any]:
    """Return a fail-closed unavailable signal payload."""

    return {
        "symbol": symbol.strip().upper() or "RELIANCE",
        "decision": DATA_UNAVAILABLE,
        "entry": DATA_UNAVAILABLE,
        "stop_loss": DATA_UNAVAILABLE,
        "target_1": DATA_UNAVAILABLE,
        "target_2": DATA_UNAVAILABLE,
        "risk_reward": DATA_UNAVAILABLE,
        "confidence_score": 0,
        "signal_reasons": (reason,),
        "validation_status": DATA_UNAVAILABLE,
        "data_source": DATA_UNAVAILABLE,
        "timestamp": datetime.now(UTC).isoformat(),
        "market_regime": DATA_UNAVAILABLE,
        "multi_timeframe_alignment": False,
        "support_resistance": {
            "support": DATA_UNAVAILABLE,
            "resistance": DATA_UNAVAILABLE,
            "distance_to_support_atr": DATA_UNAVAILABLE,
            "distance_to_resistance_atr": DATA_UNAVAILABLE,
        },
        "timeframes": {
            "primary_5m": DATA_UNAVAILABLE,
            "confirmation_15m": DATA_UNAVAILABLE,
            "trend_1h": DATA_UNAVAILABLE,
        },
        "indicators": _unavailable_indicators(),
        "go_live_allowed": False,
    }


def accuracy_report(symbol: str, trade_history: Sequence[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """Return an accuracy report without inventing win rate or profit factor."""

    history = tuple(trade_history or ())
    if not history:
        return {
            "symbol": symbol.strip().upper() or "RELIANCE",
            "total_signals": 0,
            "buy_signals": 0,
            "sell_signals": 0,
            "no_trade_count": 0,
            "win_rate": DATA_UNAVAILABLE,
            "profit_factor": DATA_UNAVAILABLE,
            "max_drawdown": DATA_UNAVAILABLE,
            "validation_status": DATA_UNAVAILABLE,
            "reason": "NO_TRADE_HISTORY_AVAILABLE",
            "go_live_allowed": False,
        }

    buy_signals = sum(1 for row in history if str(row.get("decision", "")).upper() == "BUY")
    sell_signals = sum(1 for row in history if str(row.get("decision", "")).upper() == "SELL")
    no_trade_count = sum(1 for row in history if str(row.get("decision", "")).upper() == NO_TRADE)
    pnl_values = [_safe_float(row.get("pnl"), 0.0) for row in history if row.get("pnl") is not None]
    winning = [value for value in pnl_values if value > 0]
    losing = [value for value in pnl_values if value < 0]
    win_rate: float | str = DATA_UNAVAILABLE
    profit_factor: float | str = DATA_UNAVAILABLE
    if pnl_values:
        win_rate = round((len(winning) / len(pnl_values)) * 100, 2)
    if losing:
        profit_factor = round(sum(winning) / abs(sum(losing)), 2)
    elif winning:
        profit_factor = "INF"
    return {
        "symbol": symbol.strip().upper() or "RELIANCE",
        "total_signals": len(history),
        "buy_signals": buy_signals,
        "sell_signals": sell_signals,
        "no_trade_count": no_trade_count,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "max_drawdown": _max_drawdown(pnl_values) if pnl_values else DATA_UNAVAILABLE,
        "validation_status": "VALIDATED" if pnl_values else DATA_UNAVAILABLE,
        "go_live_allowed": False,
    }


def signal_from_candles(
    symbol: str,
    primary_candles: Sequence[Mapping[str, Any]],
    confirmation_candles: Sequence[Mapping[str, Any]] | None = None,
    trend_candles: Sequence[Mapping[str, Any]] | None = None,
    *,
    data_source: str = "ZERODHA_KITE_HISTORICAL",
) -> dict[str, Any]:
    """Build a strict multi-layer signal from real candle payloads only."""

    normalized = symbol.strip().upper() or "RELIANCE"
    primary = _clean_candles(primary_candles)
    confirmation = _clean_candles(confirmation_candles or primary_candles)
    trend = _clean_candles(trend_candles or confirmation_candles or primary_candles)

    if len(primary) < 21:
        return signal_unavailable(normalized, "INSUFFICIENT_PRIMARY_5M_CANDLES")
    if len(confirmation) < 21:
        return signal_unavailable(normalized, "INSUFFICIENT_CONFIRMATION_15M_CANDLES")
    if len(trend) < 21:
        return signal_unavailable(normalized, "INSUFFICIENT_TREND_1H_CANDLES")

    primary_state = _analyze_timeframe(primary, "5m")
    confirmation_state = _analyze_timeframe(confirmation, "15m")
    trend_state = _analyze_timeframe(trend, "1h")
    reasons: list[str] = []
    score = 0

    directions = (primary_state["direction"], confirmation_state["direction"], trend_state["direction"])
    alignment = len(set(directions)) == 1 and directions[0] in {"BULLISH", "BEARISH"}
    if alignment:
        score += 25
        reasons.append("MULTI_TIMEFRAME_ALIGNED")
    else:
        reasons.append("MULTI_TIMEFRAME_CONFLICT")

    market_regime = _market_regime(primary_state, confirmation_state, trend_state)
    if market_regime in {"TRENDING_UP", "TRENDING_DOWN"}:
        score += 15
        reasons.append(f"REGIME_{market_regime}")
    else:
        reasons.append(f"REGIME_{market_regime}")

    last_close = primary_state["last_close"]
    atr = max(primary_state["atr_14"], 0.01)
    support = primary_state["support"]
    resistance = primary_state["resistance"]
    distance_to_resistance_atr = (resistance - last_close) / atr
    distance_to_support_atr = (last_close - support) / atr
    support_resistance_ok = True

    if directions[0] == "BULLISH":
        if distance_to_resistance_atr <= 1.0:
            support_resistance_ok = False
            reasons.append("BUY_TOO_CLOSE_TO_RESISTANCE")
        else:
            score += 10
            reasons.append("BUY_HAS_RESISTANCE_ROOM")
    elif directions[0] == "BEARISH":
        if distance_to_support_atr <= 1.0:
            support_resistance_ok = False
            reasons.append("SELL_TOO_CLOSE_TO_SUPPORT")
        else:
            score += 10
            reasons.append("SELL_HAS_SUPPORT_ROOM")

    if primary_state["ema_alignment"]:
        score += 12
        reasons.append("EMA_ALIGNMENT_PASS")
    if primary_state["vwap_alignment"]:
        score += 10
        reasons.append("VWAP_ALIGNMENT_PASS")
    if primary_state["rsi_ok"]:
        score += 10
        reasons.append("RSI_ZONE_PASS")
    else:
        reasons.append("RSI_ZONE_BLOCK")
    if primary_state["atr_ok"]:
        score += 8
        reasons.append("ATR_VOLATILITY_PASS")
    else:
        reasons.append("ATR_VOLATILITY_BLOCK")
    if primary_state["volume_confirmation"]:
        score += 10
        reasons.append("VOLUME_CONFIRMATION_PASS")
    else:
        reasons.append("LOW_VOLUME_BLOCK")

    direction = directions[0] if alignment else "CONFLICT"
    side: str | None = None
    decision = NO_TRADE
    if (
        alignment
        and support_resistance_ok
        and primary_state["volume_confirmation"]
        and market_regime not in {"SIDEWAYS", "LOW_VOLUME", "HIGH_VOLATILITY"}
        and score >= 75
        and direction == "BULLISH"
    ):
        decision = "BUY"
        side = "BUY"
    elif (
        alignment
        and support_resistance_ok
        and primary_state["volume_confirmation"]
        and market_regime not in {"SIDEWAYS", "LOW_VOLUME", "HIGH_VOLATILITY"}
        and score >= 75
        and direction == "BEARISH"
    ):
        decision = "SELL"
        side = "SELL"
    elif 55 <= score < 75 and alignment:
        decision = "HOLD"
        reasons.append("CONFIDENCE_55_TO_74_HOLD")
    elif not alignment:
        reasons.append("TIMEFRAME_DISAGREEMENT_NO_TRADE")
    else:
        reasons.append("STRICT_FILTER_NO_TRADE")

    entry: float | str = round(last_close, 2) if decision in {"BUY", "SELL", "HOLD"} else DATA_UNAVAILABLE
    stop_loss: float | str = DATA_UNAVAILABLE
    target_1: float | str = DATA_UNAVAILABLE
    target_2: float | str = DATA_UNAVAILABLE
    risk_reward: float | str = DATA_UNAVAILABLE
    if side == "BUY":
        stop_loss = round(last_close - atr, 2)
        target_1 = round(last_close + (atr * 2), 2)
        target_2 = round(last_close + (atr * 3), 2)
        risk_reward = 2.0
    elif side == "SELL":
        stop_loss = round(last_close + atr, 2)
        target_1 = round(last_close - (atr * 2), 2)
        target_2 = round(last_close - (atr * 3), 2)
        risk_reward = 2.0

    return {
        "symbol": normalized,
        "decision": decision,
        "entry": entry,
        "stop_loss": stop_loss,
        "target_1": target_1,
        "target_2": target_2,
        "risk_reward": risk_reward,
        "confidence_score": min(100, round(score, 2)),
        "signal_reasons": tuple(dict.fromkeys(reasons)),
        "validation_status": "VALIDATED",
        "data_source": data_source,
        "timestamp": datetime.now(UTC).isoformat(),
        "market_regime": market_regime,
        "multi_timeframe_alignment": alignment,
        "support_resistance": {
            "support": round(support, 2),
            "resistance": round(resistance, 2),
            "distance_to_support_atr": round(distance_to_support_atr, 2),
            "distance_to_resistance_atr": round(distance_to_resistance_atr, 2),
        },
        "timeframes": {
            "primary_5m": primary_state["direction"],
            "confirmation_15m": confirmation_state["direction"],
            "trend_1h": trend_state["direction"],
        },
        "indicators": {
            "ema_9": round(primary_state["ema_9"], 2),
            "ema_21": round(primary_state["ema_21"], 2),
            "vwap": round(primary_state["vwap"], 2),
            "rsi_14": round(primary_state["rsi_14"], 2),
            "atr_14": round(primary_state["atr_14"], 2),
            "volume_confirmation": primary_state["volume_confirmation"],
            "trend_direction": primary_state["direction"],
            "market_regime": market_regime,
            "multi_timeframe_alignment": alignment,
            "support": round(support, 2),
            "resistance": round(resistance, 2),
        },
        "go_live_allowed": False,
    }


def _analyze_timeframe(candles: list[dict[str, float]], label: str) -> dict[str, Any]:
    closes = [row["close"] for row in candles]
    highs = [row["high"] for row in candles]
    lows = [row["low"] for row in candles]
    volumes = [row["volume"] for row in candles]
    ema_9 = _ema(closes, 9)
    ema_21 = _ema(closes, 21)
    vwap = _vwap(candles)
    rsi_14 = _rsi(closes, 14)
    atr_14 = _atr(highs, lows, closes, 14)
    last_close = closes[-1]
    avg_volume = sum(volumes[-20:]) / min(len(volumes), 20)
    volume_confirmation = volumes[-1] >= avg_volume and volumes[-1] > 0
    atr_ratio = atr_14 / last_close if last_close else 0.0
    direction = "BULLISH" if ema_9 > ema_21 and last_close > vwap else "BEARISH" if ema_9 < ema_21 and last_close < vwap else "SIDEWAYS"
    if _sideways(closes, atr_14):
        direction = "SIDEWAYS"
    return {
        "label": label,
        "direction": direction,
        "ema_9": ema_9,
        "ema_21": ema_21,
        "vwap": vwap,
        "rsi_14": rsi_14,
        "atr_14": atr_14,
        "last_close": last_close,
        "support": min(lows[-20:]),
        "resistance": max(highs[-20:]),
        "volume_confirmation": volume_confirmation,
        "atr_ratio": atr_ratio,
        "ema_alignment": direction in {"BULLISH", "BEARISH"},
        "vwap_alignment": (direction == "BULLISH" and last_close > vwap) or (direction == "BEARISH" and last_close < vwap),
        "rsi_ok": (direction == "BULLISH" and 45 <= rsi_14 <= 68) or (direction == "BEARISH" and 32 <= rsi_14 <= 55),
        "atr_ok": 0.0005 <= atr_ratio <= 0.035,
    }


def _market_regime(primary: Mapping[str, Any], confirmation: Mapping[str, Any], trend: Mapping[str, Any]) -> str:
    if not primary["volume_confirmation"]:
        return "LOW_VOLUME"
    if primary["atr_ratio"] > 0.035:
        return "HIGH_VOLATILITY"
    directions = (primary["direction"], confirmation["direction"], trend["direction"])
    if directions == ("BULLISH", "BULLISH", "BULLISH"):
        return "TRENDING_UP"
    if directions == ("BEARISH", "BEARISH", "BEARISH"):
        return "TRENDING_DOWN"
    if "SIDEWAYS" in directions:
        return "SIDEWAYS"
    return "SIDEWAYS"


def _clean_candles(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, float]]:
    clean = []
    for row in rows:
        try:
            clean.append(
                {
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row.get("volume", 0) or 0),
                }
            )
        except (KeyError, TypeError, ValueError):
            continue
    return clean


def _unavailable_indicators() -> dict[str, Any]:
    return {
        "ema_9": DATA_UNAVAILABLE,
        "ema_21": DATA_UNAVAILABLE,
        "vwap": DATA_UNAVAILABLE,
        "rsi_14": DATA_UNAVAILABLE,
        "atr_14": DATA_UNAVAILABLE,
        "volume_confirmation": DATA_UNAVAILABLE,
        "trend_direction": DATA_UNAVAILABLE,
        "market_regime": DATA_UNAVAILABLE,
        "multi_timeframe_alignment": False,
        "support": DATA_UNAVAILABLE,
        "resistance": DATA_UNAVAILABLE,
    }


def _ema(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    seed = values[:period] if len(values) >= period else values
    ema = sum(seed) / len(seed)
    multiplier = 2 / (period + 1)
    for value in values[len(seed):]:
        ema = (value - ema) * multiplier + ema
    return ema


def _vwap(candles: list[dict[str, float]]) -> float:
    total_pv = 0.0
    total_volume = 0.0
    for row in candles:
        typical = (row["high"] + row["low"] + row["close"]) / 3
        volume = max(row["volume"], 1.0)
        total_pv += typical * volume
        total_volume += volume
    return total_pv / total_volume if total_volume else candles[-1]["close"]


def _rsi(closes: list[float], period: int) -> float:
    if len(closes) <= period:
        return 50.0
    gains = []
    losses = []
    for prev, current in zip(closes[-period - 1:-1], closes[-period:]):
        change = current - prev
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0 if avg_gain else 50.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _atr(highs: list[float], lows: list[float], closes: list[float], period: int) -> float:
    if len(closes) < 2:
        return 0.0
    trs = []
    for index in range(1, len(closes)):
        trs.append(max(highs[index] - lows[index], abs(highs[index] - closes[index - 1]), abs(lows[index] - closes[index - 1])))
    recent = trs[-period:] if len(trs) >= period else trs
    return sum(recent) / len(recent) if recent else 0.0


def _sideways(closes: list[float], atr: float) -> bool:
    if len(closes) < 20:
        return True
    recent = closes[-20:]
    price_range = max(recent) - min(recent)
    return price_range <= max(atr * 1.5, recent[-1] * 0.001)


def _max_drawdown(pnl_values: Sequence[float]) -> float:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for value in pnl_values:
        equity += value
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
    return round(abs(max_dd), 2)


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
