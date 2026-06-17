"""Safe trade-plan builder for paper/shadow signal enrichment.

This module never fabricates market data and never enables live trading. It only
uses validated quotes and validated candle data to build an auditable plan for
paper/shadow review. Weak or incomplete evidence returns NO_TRADE or
DATA_UNAVAILABLE.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
NO_TRADE = "NO_TRADE"
_ALLOWED_ACTIONS = {"BUY", "SELL", "HOLD", NO_TRADE, DATA_UNAVAILABLE}


@dataclass(frozen=True)
class SafeTradePlan:
    symbol: str
    original_action: str
    final_action: str
    entry: float | str
    stop_loss: float | str
    target_1: float | str
    target_2: float | str
    risk_reward: float | str
    expected_move_points: float | str
    confidence_score: float | str
    confidence_grade: str
    atr: float | str
    support: float | str
    resistance: float | str
    blocked_reasons: tuple[str, ...]
    notes: tuple[str, ...]
    validation_status: str
    data_source: str
    can_place_real_order: bool = False
    go_live_allowed: bool = False

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["blocked_reasons"] = list(self.blocked_reasons)
        payload["notes"] = list(self.notes)
        return payload


class SafeTradePlanBuilder:
    """Builds complete trade-plan fields only from validated evidence."""

    def __init__(self, *, min_confidence: float | None = None, min_risk_reward: float | None = None) -> None:
        self.min_confidence = min_confidence if min_confidence is not None else _safe_float(os.environ.get("MIN_SIGNAL_CONFIDENCE"), 70.0)
        self.min_risk_reward = min_risk_reward if min_risk_reward is not None else _safe_float(os.environ.get("MIN_RISK_REWARD"), 1.5)

    def build(
        self,
        *,
        symbol: str = "RELIANCE",
        signal: Mapping[str, Any] | None = None,
        market_quote: Mapping[str, Any] | None = None,
        market_history: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        signal = signal or {}
        quote = _normalise_quote_payload(market_quote or {})
        history = market_history or {}
        candles = _normalise_candles(history.get("candles") or [])
        symbol = (symbol or str(signal.get("symbol") or quote.get("symbol") or "RELIANCE")).strip().upper() or "RELIANCE"

        reasons: list[str] = []
        notes: list[str] = []
        original_action = _canonical_action(signal)

        quote_status = str(quote.get("validation_status", DATA_UNAVAILABLE)).upper()
        ltp = quote.get("ltp", quote.get("last_price"))
        if quote_status != "VALIDATED" or not isinstance(ltp, (int, float)) or ltp <= 0:
            reasons.append("VALIDATED_QUOTE_REQUIRED")

        history_status = str(history.get("validation_status", DATA_UNAVAILABLE)).upper()
        if history_status != "VALIDATED":
            reasons.append("VALIDATED_CANDLES_REQUIRED")
        if len(candles) < 21:
            reasons.append("MINIMUM_21_CANDLES_REQUIRED")

        confidence = _safe_float(signal.get("confidence_score", signal.get("confidence")), -1.0)
        if confidence < 0:
            reasons.append("CONFIDENCE_REQUIRED")
        elif confidence < self.min_confidence:
            reasons.append(f"CONFIDENCE_BELOW_{int(self.min_confidence)}")

        if "VALIDATED_QUOTE_REQUIRED" in reasons or "VALIDATED_CANDLES_REQUIRED" in reasons or "MINIMUM_21_CANDLES_REQUIRED" in reasons:
            return self._blocked(
                symbol,
                original_action,
                DATA_UNAVAILABLE,
                reasons,
                notes,
                confidence,
                data_source=str(quote.get("data_source") or history.get("data_source") or DATA_UNAVAILABLE),
            )

        entry = float(ltp)
        atr = _safe_float(_deep_get(signal, ("indicators", "atr_14")), 0.0)
        if atr <= 0:
            atr = _average_true_range(candles[-21:])
        support = _safe_float(_deep_get(signal, ("market_structure", "support")), 0.0)
        if support <= 0:
            support = _safe_float(_deep_get(signal, ("indicators", "support")), 0.0)
        if support <= 0:
            support = min(c["low"] for c in candles[-20:])
        resistance = _safe_float(_deep_get(signal, ("market_structure", "resistance")), 0.0)
        if resistance <= 0:
            resistance = _safe_float(_deep_get(signal, ("indicators", "resistance")), 0.0)
        if resistance <= 0:
            resistance = max(c["high"] for c in candles[-20:])

        if atr <= 0:
            reasons.append("ATR_REQUIRED")
        if support <= 0:
            reasons.append("SUPPORT_REQUIRED")
        if resistance <= 0:
            reasons.append("RESISTANCE_REQUIRED")

        action = _derive_safe_action(original_action=original_action, signal=signal)
        if action not in {"BUY", "SELL"}:
            reasons.append("DIRECTIONAL_EVIDENCE_NOT_STRONG_ENOUGH")

        if reasons:
            return self._blocked(symbol, original_action, NO_TRADE, reasons, notes, confidence, atr=atr, support=support, resistance=resistance, data_source=str(quote.get("data_source") or history.get("data_source") or DATA_UNAVAILABLE))

        if action == "BUY":
            stop_loss = min(entry - atr, support - (0.10 * atr))
            risk = entry - stop_loss
            minimum_target = entry + (risk * self.min_risk_reward)
            target_1 = max(resistance, minimum_target)
            target_2 = max(target_1 + risk, entry + (risk * (self.min_risk_reward + 1.0)))
            if stop_loss <= 0 or stop_loss >= entry:
                reasons.append("VALID_BUY_STOP_LOSS_REQUIRED")
            if target_1 <= entry:
                reasons.append("VALID_BUY_TARGET_REQUIRED")
        else:
            stop_loss = max(entry + atr, resistance + (0.10 * atr))
            risk = stop_loss - entry
            minimum_target = entry - (risk * self.min_risk_reward)
            target_1 = min(support, minimum_target)
            target_2 = min(target_1 - risk, entry - (risk * (self.min_risk_reward + 1.0)))
            if stop_loss <= entry:
                reasons.append("VALID_SELL_STOP_LOSS_REQUIRED")
            if target_1 >= entry or target_1 <= 0:
                reasons.append("VALID_SELL_TARGET_REQUIRED")

        risk_reward = 0.0
        if risk > 0:
            reward = abs(target_1 - entry)
            risk_reward = round(reward / risk, 2)
        if risk_reward < self.min_risk_reward:
            reasons.append(f"RISK_REWARD_BELOW_{self.min_risk_reward}")
        if not _all_positive(entry, stop_loss, target_1, target_2):
            reasons.append("COMPLETE_TRADE_PLAN_REQUIRED")

        if reasons:
            return self._blocked(symbol, original_action, NO_TRADE, reasons, notes, confidence, atr=atr, support=support, resistance=resistance, data_source=str(quote.get("data_source") or history.get("data_source") or DATA_UNAVAILABLE))

        notes.append("Safe trade plan built from validated quote and candle evidence for paper/shadow review only.")
        return SafeTradePlan(
            symbol=symbol,
            original_action=original_action,
            final_action=action,
            entry=round(entry, 2),
            stop_loss=round(stop_loss, 2),
            target_1=round(target_1, 2),
            target_2=round(target_2, 2),
            risk_reward=risk_reward,
            expected_move_points=round(max(atr, abs(target_1 - entry)), 2),
            confidence_score=round(confidence, 2),
            confidence_grade=_confidence_grade(confidence),
            atr=round(atr, 2),
            support=round(support, 2),
            resistance=round(resistance, 2),
            blocked_reasons=(),
            notes=tuple(notes),
            validation_status="VALIDATED",
            data_source=str(quote.get("data_source") or history.get("data_source") or "SAFE_TRADE_PLAN_BUILDER"),
            can_place_real_order=False,
            go_live_allowed=False,
        ).as_dict()

    def _blocked(
        self,
        symbol: str,
        original_action: str,
        final_action: str,
        reasons: list[str],
        notes: list[str],
        confidence: float,
        *,
        atr: float | str = DATA_UNAVAILABLE,
        support: float | str = DATA_UNAVAILABLE,
        resistance: float | str = DATA_UNAVAILABLE,
        data_source: str = DATA_UNAVAILABLE,
    ) -> dict[str, Any]:
        return SafeTradePlan(
            symbol=symbol,
            original_action=original_action,
            final_action=final_action if final_action in _ALLOWED_ACTIONS else NO_TRADE,
            entry=DATA_UNAVAILABLE,
            stop_loss=DATA_UNAVAILABLE,
            target_1=DATA_UNAVAILABLE,
            target_2=DATA_UNAVAILABLE,
            risk_reward=DATA_UNAVAILABLE,
            expected_move_points=round(atr, 2) if isinstance(atr, (int, float)) and atr > 0 else DATA_UNAVAILABLE,
            confidence_score=round(confidence, 2) if confidence >= 0 else DATA_UNAVAILABLE,
            confidence_grade=_confidence_grade(confidence),
            atr=round(atr, 2) if isinstance(atr, (int, float)) and atr > 0 else DATA_UNAVAILABLE,
            support=round(support, 2) if isinstance(support, (int, float)) and support > 0 else DATA_UNAVAILABLE,
            resistance=round(resistance, 2) if isinstance(resistance, (int, float)) and resistance > 0 else DATA_UNAVAILABLE,
            blocked_reasons=tuple(dict.fromkeys(reasons)),
            notes=tuple(dict.fromkeys(notes)),
            validation_status="BLOCKED" if final_action == NO_TRADE else DATA_UNAVAILABLE,
            data_source=data_source,
            can_place_real_order=False,
            go_live_allowed=False,
        ).as_dict()


def build_safe_trade_plan(
    *,
    symbol: str = "RELIANCE",
    signal: Mapping[str, Any] | None = None,
    market_quote: Mapping[str, Any] | None = None,
    market_history: Mapping[str, Any] | None = None,
    min_confidence: float | None = None,
    min_risk_reward: float | None = None,
) -> dict[str, Any]:
    return SafeTradePlanBuilder(min_confidence=min_confidence, min_risk_reward=min_risk_reward).build(symbol=symbol, signal=signal or {}, market_quote=market_quote or {}, market_history=market_history or {})


def enrich_signal_with_safe_trade_plan(
    signal: Mapping[str, Any],
    *,
    symbol: str,
    market_quote: Mapping[str, Any],
    market_history: Mapping[str, Any],
) -> dict[str, Any]:
    payload = dict(signal)
    plan = build_safe_trade_plan(symbol=symbol, signal=payload, market_quote=market_quote, market_history=market_history)
    payload["safe_trade_plan"] = plan
    payload["final_action"] = plan["final_action"]
    payload["decision"] = plan["final_action"]
    for key in ("entry", "stop_loss", "target_1", "target_2", "risk_reward", "expected_move_points", "confidence_grade"):
        payload[key] = plan[key]
    payload["safe_trade_plan_status"] = plan["validation_status"]
    payload["safe_trade_plan_blocked_reasons"] = tuple(plan.get("blocked_reasons") or [])
    if plan["final_action"] in {"BUY", "SELL"}:
        payload["validation_status"] = "VALIDATED"
    elif plan["final_action"] == DATA_UNAVAILABLE:
        payload["validation_status"] = DATA_UNAVAILABLE
    else:
        payload["validation_status"] = "NO_TRADE_SAFE_PLAN_BLOCKED"
    reasons = list(payload.get("signal_reasons") or [])
    reasons.extend(plan.get("blocked_reasons") or [])
    payload["signal_reasons"] = tuple(dict.fromkeys(str(reason) for reason in reasons if str(reason)))
    payload["go_live_allowed"] = False
    return payload


def _derive_safe_action(*, original_action: str, signal: Mapping[str, Any]) -> str:
    if original_action in {"BUY", "SELL"}:
        return original_action

    timeframes = signal.get("timeframes") if isinstance(signal.get("timeframes"), Mapping) else {}
    indicators = signal.get("indicators") if isinstance(signal.get("indicators"), Mapping) else {}
    values = [str(value).upper() for value in timeframes.values()] + [str(indicators.get("trend_direction", "")).upper()]
    bullish_votes = sum(1 for value in values if "BULLISH" in value or value == "UP")
    bearish_votes = sum(1 for value in values if "BEARISH" in value or value == "DOWN")
    volume_ok = bool(indicators.get("volume_confirmation", False))
    if bullish_votes >= 3 and bullish_votes > bearish_votes and volume_ok:
        return "BUY"
    if bearish_votes >= 3 and bearish_votes > bullish_votes and volume_ok:
        return "SELL"
    return NO_TRADE


def _normalise_quote_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(payload.get("data"), Mapping):
        merged = dict(payload["data"])
        for key in ("status", "read_only", "mutation_enabled", "go_live_allowed"):
            if key in payload:
                merged[key] = payload[key]
        if "validation_status" not in merged and payload.get("status") == "CONNECTED":
            merged["validation_status"] = "VALIDATED"
        return merged
    return dict(payload)


def _normalise_candles(candles: Any) -> list[dict[str, float]]:
    if not isinstance(candles, (list, tuple)):
        return []
    rows: list[dict[str, float]] = []
    for candle in candles:
        if not isinstance(candle, Mapping):
            continue
        row = {key: _safe_float(candle.get(key), 0.0) for key in ("open", "high", "low", "close")}
        if all(value > 0 for value in row.values()):
            rows.append(row)
    return rows


def _average_true_range(candles: Sequence[Mapping[str, float]], period: int = 14) -> float:
    rows = list(candles)
    if len(rows) < period + 1:
        return 0.0
    trs: list[float] = []
    for index in range(1, len(rows)):
        current = rows[index]
        previous = rows[index - 1]
        high = float(current["high"])
        low = float(current["low"])
        previous_close = float(previous["close"])
        trs.append(max(high - low, abs(high - previous_close), abs(low - previous_close)))
    window = trs[-period:]
    return round(sum(window) / len(window), 4) if window else 0.0


def _canonical_action(signal: Mapping[str, Any]) -> str:
    action = str(signal.get("final_action", signal.get("decision", signal.get("action", DATA_UNAVAILABLE)))).strip().upper()
    return action if action in _ALLOWED_ACTIONS else DATA_UNAVAILABLE


def _deep_get(payload: Mapping[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = payload
    for key in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _confidence_grade(confidence: float) -> str:
    if confidence < 0:
        return DATA_UNAVAILABLE
    if confidence >= 90:
        return "A"
    if confidence >= 80:
        return "B"
    if confidence >= 70:
        return "C"
    if confidence >= 60:
        return "D"
    return "F"


def _all_positive(*values: float) -> bool:
    return all(isinstance(value, (int, float)) and value > 0 for value in values)
