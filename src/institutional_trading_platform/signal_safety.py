"""Safe signal wrapper for ALPHA-GATE X.

Phase 4 is additive: it preserves the existing signal engine and normalizes its
output into a safer, fail-closed contract for later risk-engine phases.
"""

from __future__ import annotations

from datetime import datetime, UTC
from typing import Any, Mapping, Sequence

from .market_data_safety import DATA_UNAVAILABLE, is_actionable_data_allowed
from .safe_config import getTradingConfig

_ALLOWED_ACTIONS = {"BUY", "SELL", "HOLD", "NO_TRADE", "DATA_UNAVAILABLE"}


def safe_signal_from_existing_signal(
    symbol: str,
    existing_signal: Mapping[str, Any],
    market_health: Mapping[str, Any],
    *,
    timeframe: str = "5minute",
    min_confidence: float | None = None,
) -> dict[str, Any]:
    """Normalize an existing signal payload into the Phase 4 safe contract."""

    normalized_symbol = (symbol or str(existing_signal.get("symbol") or "RELIANCE")).strip().upper()
    threshold = getTradingConfig().riskLimits.minSignalConfidence if min_confidence is None else float(min_confidence)
    now = str(existing_signal.get("timestamp") or datetime.now(UTC).isoformat())

    health_state = str(market_health.get("state", DATA_UNAVAILABLE))
    data_quality = _data_quality_from_health(health_state, bool(market_health.get("missingData")))
    reasons = _as_string_list(existing_signal.get("signal_reasons") or existing_signal.get("reasons") or ())
    blocked: list[str] = _as_string_list(existing_signal.get("blocked_reasons") or ())

    if not is_actionable_data_allowed(market_health):
        blocked.extend(_as_string_list(market_health.get("blockedReasons") or ("MARKET_DATA_NOT_ACTIONABLE",)))
        return _payload(
            symbol=normalized_symbol,
            timeframe=timeframe,
            action="DATA_UNAVAILABLE",
            entry=None,
            stop_loss=None,
            targets=(),
            confidence=_confidence(existing_signal),
            expected_move_points=_number_or_none(existing_signal.get("expected_move_points") or existing_signal.get("expected_move")),
            risk_reward=None,
            regime=_regime(existing_signal, reasons),
            reasons=reasons,
            blocked_reasons=blocked,
            timestamp=now,
            data_quality=data_quality,
        )

    raw_action = str(existing_signal.get("action") or existing_signal.get("decision") or "DATA_UNAVAILABLE").strip().upper()
    action = raw_action if raw_action in _ALLOWED_ACTIONS else "DATA_UNAVAILABLE"
    if action == "NO TRADE":
        action = "NO_TRADE"

    entry = _number_or_none(existing_signal.get("entry"))
    stop_loss = _number_or_none(existing_signal.get("stop_loss"))
    targets = _targets(existing_signal)
    confidence = _confidence(existing_signal)
    risk_reward = _number_or_none(existing_signal.get("risk_reward"))
    expected_move = _number_or_none(existing_signal.get("expected_move_points") or existing_signal.get("expected_move"))

    if action in {"BUY", "SELL"}:
        if stop_loss is None:
            blocked.append("STOP_LOSS_REQUIRED")
        if not targets:
            blocked.append("TARGET_REQUIRED")
        if risk_reward is None:
            blocked.append("RISK_REWARD_REQUIRED")
        if confidence < threshold:
            blocked.append("CONFIDENCE_BELOW_MINIMUM")
        if blocked:
            action = "NO_TRADE"
            data_quality = "INSUFFICIENT" if data_quality == "GOOD" else data_quality
    elif action == "DATA_UNAVAILABLE":
        data_quality = "MISSING"
    elif confidence < threshold and action in {"HOLD", "NO_TRADE"}:
        blocked.append("LOW_CONFIDENCE_NON_ACTIONABLE")

    return _payload(
        symbol=normalized_symbol,
        timeframe=timeframe,
        action=action,
        entry=entry,
        stop_loss=stop_loss,
        targets=targets,
        confidence=confidence,
        expected_move_points=expected_move,
        risk_reward=risk_reward,
        regime=_regime(existing_signal, reasons),
        reasons=reasons,
        blocked_reasons=blocked,
        timestamp=now,
        data_quality=data_quality,
    )


def _payload(
    *,
    symbol: str,
    timeframe: str,
    action: str,
    entry: float | None,
    stop_loss: float | None,
    targets: Sequence[float],
    confidence: float,
    expected_move_points: float | None,
    risk_reward: float | None,
    regime: str,
    reasons: Sequence[str],
    blocked_reasons: Sequence[str],
    timestamp: str,
    data_quality: str,
) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "action": action,
        "entry": entry,
        "stop_loss": stop_loss,
        "targets": tuple(targets),
        "confidence": confidence,
        "confidence_grade": confidence_grade(confidence),
        "expected_move_points": expected_move_points,
        "risk_reward": risk_reward,
        "regime": regime,
        "reasons": tuple(reasons),
        "blocked_reasons": tuple(dict.fromkeys(blocked_reasons)),
        "timestamp": timestamp,
        "data_quality": data_quality,
        "go_live_allowed": False,
    }


def confidence_grade(confidence: float) -> str:
    if confidence >= 85:
        return "A"
    if confidence >= 75:
        return "B"
    if confidence >= 65:
        return "C"
    if confidence >= 50:
        return "D"
    return "F"


def _confidence(signal: Mapping[str, Any]) -> float:
    value = signal.get("confidence")
    if value is None:
        value = signal.get("confidence_score")
    number = _number_or_none(value)
    return max(0.0, min(100.0, number if number is not None else 0.0))


def _targets(signal: Mapping[str, Any]) -> tuple[float, ...]:
    raw_targets = signal.get("targets")
    values: list[float] = []
    if isinstance(raw_targets, Sequence) and not isinstance(raw_targets, (str, bytes)):
        for item in raw_targets:
            number = _number_or_none(item)
            if number is not None:
                values.append(number)
    for key in ("target_1", "target_2", "target_3"):
        number = _number_or_none(signal.get(key))
        if number is not None:
            values.append(number)
    return tuple(dict.fromkeys(values))


def _regime(signal: Mapping[str, Any], reasons: Sequence[str]) -> str:
    raw = str(signal.get("regime") or signal.get("trend_regime") or "").upper()
    if raw in {"TRENDING", "RANGE", "VOLATILE", "LOW_VOLUME", "UNKNOWN"}:
        return raw
    joined = " ".join(reasons).upper()
    if "LOW_VOLUME" in joined or "LOW VOLUME" in joined:
        return "LOW_VOLUME"
    if "VOLATILE" in joined or "HIGH_VOL" in joined:
        return "VOLATILE"
    if "TREND" in joined:
        return "TRENDING"
    if "RANGE" in joined:
        return "RANGE"
    return "UNKNOWN"


def _data_quality_from_health(state: str, missing: bool) -> str:
    if missing or state == DATA_UNAVAILABLE:
        return "MISSING"
    if state in {"STALE", "RECONNECTING", "DISCONNECTED"}:
        return "STALE"
    if state == "CONNECTED":
        return "GOOD"
    return "INSUFFICIENT"


def _number_or_none(value: Any) -> float | None:
    if value in (None, "", DATA_UNAVAILABLE):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_string_list(value: Any) -> list[str]:
    if value in (None, "", DATA_UNAVAILABLE):
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Sequence):
        return [str(item) for item in value]
    return [str(value)]
