"""Clean-room Quant Trader style adapter.

This module is inspired by the public systemtrader/quant_trader README architecture:
market data -> multi-timeframe K-line collection -> strategy decision -> target
position instruction. It does not copy GPL source code and it never places real
broker orders.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from statistics import mean
from typing import Any, Mapping, Sequence

DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
NO_TRADE = "NO_TRADE"
GO_LIVE_ALLOWED = False


@dataclass(frozen=True)
class CandleBucket:
    timeframe: str
    ready: bool
    candle_count: int
    last_close: float | str
    trend: str
    validation_status: str
    go_live_allowed: bool = GO_LIVE_ALLOWED


@dataclass(frozen=True)
class TargetPositionInstruction:
    symbol: str
    decision: str
    target_position: int
    current_position: int
    delta: int
    instruction: str
    stop_loss: float | str
    target_1: float | str
    target_2: float | str
    buckets: tuple[CandleBucket, ...]
    reasons: tuple[str, ...]
    execution_status: str
    go_live_allowed: bool = GO_LIVE_ALLOWED

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["buckets"] = tuple(asdict(row) for row in self.buckets)
        payload["go_live_allowed"] = False
        return payload


class QuantTraderStyleAdapter:
    """Multi-timeframe target-position engine, paper/shadow only."""

    required_timeframes = ("1m", "5m", "15m", "60m")

    def evaluate(
        self,
        symbol: str,
        histories: Mapping[str, Mapping[str, Any]],
        *,
        current_position: int = 0,
    ) -> dict[str, Any]:
        normalized = (symbol or "RELIANCE").strip().upper()
        buckets = tuple(self._bucket(tf, histories.get(tf, {})) for tf in self.required_timeframes)

        if not all(bucket.ready for bucket in buckets):
            missing = tuple(bucket.timeframe for bucket in buckets if not bucket.ready)
            return TargetPositionInstruction(
                symbol=normalized,
                decision=DATA_UNAVAILABLE,
                target_position=0,
                current_position=current_position,
                delta=-current_position,
                instruction="NO_TARGET_POSITION_DATA_UNAVAILABLE",
                stop_loss=DATA_UNAVAILABLE,
                target_1=DATA_UNAVAILABLE,
                target_2=DATA_UNAVAILABLE,
                buckets=buckets,
                reasons=(f"MISSING_OR_INSUFFICIENT_TIMEFRAMES:{','.join(missing)}",),
                execution_status="PAPER_SHADOW_ONLY_REAL_ORDER_DISABLED",
            ).as_dict()

        bullish = sum(1 for bucket in buckets if bucket.trend == "BULLISH")
        bearish = sum(1 for bucket in buckets if bucket.trend == "BEARISH")
        decision = NO_TRADE
        target_position = 0
        reasons: list[str] = []

        if bullish >= 3 and buckets[-1].trend == "BULLISH":
            decision = "BUY"
            target_position = 1
            reasons.append("TARGET_LONG_MULTI_TIMEFRAME_BULLISH")
        elif bearish >= 3 and buckets[-1].trend == "BEARISH":
            decision = "SELL"
            target_position = -1
            reasons.append("TARGET_SHORT_MULTI_TIMEFRAME_BEARISH")
        else:
            reasons.append("TARGET_FLAT_TIMEFRAME_CONFLICT")

        last_close = _safe_float(buckets[1].last_close) or _safe_float(buckets[0].last_close) or 0.0
        atr = self._atr(histories.get("5m", {}) or histories.get("1m", {}))
        stop_loss: float | str = DATA_UNAVAILABLE
        target_1: float | str = DATA_UNAVAILABLE
        target_2: float | str = DATA_UNAVAILABLE
        if decision == "BUY" and last_close > 0:
            stop_loss = round(last_close - atr, 2)
            target_1 = round(last_close + 2 * atr, 2)
            target_2 = round(last_close + 3 * atr, 2)
        elif decision == "SELL" and last_close > 0:
            stop_loss = round(last_close + atr, 2)
            target_1 = round(last_close - 2 * atr, 2)
            target_2 = round(last_close - 3 * atr, 2)

        delta = target_position - current_position
        instruction = "HOLD_TARGET_POSITION" if delta == 0 else "PAPER_SHADOW_TARGET_POSITION_CHANGE"

        return TargetPositionInstruction(
            symbol=normalized,
            decision=decision,
            target_position=target_position,
            current_position=current_position,
            delta=delta,
            instruction=instruction,
            stop_loss=stop_loss,
            target_1=target_1,
            target_2=target_2,
            buckets=buckets,
            reasons=tuple(dict.fromkeys(reasons)),
            execution_status="PAPER_SHADOW_ONLY_REAL_ORDER_DISABLED",
        ).as_dict()

    def _bucket(self, timeframe: str, history: Mapping[str, Any]) -> CandleBucket:
        candles = tuple(history.get("candles", ()) or ())
        if history.get("validation_status") != "VALIDATED" or len(candles) < 21:
            return CandleBucket(timeframe, False, len(candles), DATA_UNAVAILABLE, DATA_UNAVAILABLE, DATA_UNAVAILABLE)
        closes = [_safe_float(row.get("close")) for row in candles if isinstance(row, Mapping)]
        closes = [value for value in closes if value is not None]
        if len(closes) < 21:
            return CandleBucket(timeframe, False, len(closes), DATA_UNAVAILABLE, DATA_UNAVAILABLE, DATA_UNAVAILABLE)
        fast = _ema(closes, 9)
        slow = _ema(closes, 21)
        trend = "BULLISH" if fast > slow else "BEARISH" if fast < slow else "SIDEWAYS"
        return CandleBucket(timeframe, True, len(closes), round(closes[-1], 2), trend, "VALIDATED")

    def _atr(self, history: Mapping[str, Any]) -> float:
        candles = tuple(history.get("candles", ()) or ())
        trs: list[float] = []
        for idx in range(1, len(candles)):
            cur = candles[idx]
            prev = candles[idx - 1]
            if not isinstance(cur, Mapping) or not isinstance(prev, Mapping):
                continue
            high = _safe_float(cur.get("high"))
            low = _safe_float(cur.get("low"))
            prev_close = _safe_float(prev.get("close"))
            if high is None or low is None or prev_close is None:
                continue
            trs.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
        return round(mean(trs[-14:]), 2) if trs else 1.0


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except Exception:
        return None


def _ema(values: Sequence[float], period: int) -> float:
    k = 2 / (period + 1)
    ema = values[0]
    for value in values[1:]:
        ema = value * k + ema * (1 - k)
    return ema
