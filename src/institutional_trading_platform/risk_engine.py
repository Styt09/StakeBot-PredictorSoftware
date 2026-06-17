"""Central risk engine for ALPHA-GATE X.

Phase 5 is additive. It does not place broker orders and never enables real live
trading. The engine returns fail-closed risk decisions for paper, shadow, and
future live order paths.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Mapping, Sequence

from .market_data_safety import is_actionable_data_allowed
from .safe_config import TradingConfig, getTradingConfig


_ALLOWED_ACTIONS = {"BUY", "SELL"}
_DEFAULT_ALLOWED_INSTRUMENTS = {
    "RELIANCE",
    "TCS",
    "INFY",
    "HDFCBANK",
    "ICICIBANK",
    "SBIN",
    "AXISBANK",
    "NIFTY",
    "BANKNIFTY",
    "FINNIFTY",
}


@dataclass(frozen=True)
class RiskInput:
    symbol: str
    side: str
    quantity: int
    signal: Mapping[str, Any]
    market_health: Mapping[str, Any]
    account_state: Mapping[str, Any] | None = None
    open_positions: Sequence[Mapping[str, Any]] = ()
    open_orders: Sequence[Mapping[str, Any]] = ()
    order_path: str = "PAPER"
    kill_switch_active: bool = False
    broker_connected: bool = False
    position_drift_detected: bool = False
    cooldown_active: bool = False
    consecutive_losses: int = 0
    weekly_loss: float = 0.0
    max_drawdown: float = 0.0
    instrument_allowed: bool = True


class RiskEngine:
    def __init__(self, config: TradingConfig | None = None, allowed_instruments: set[str] | None = None) -> None:
        self.config = config or getTradingConfig()
        self.allowed_instruments = allowed_instruments or set(_DEFAULT_ALLOWED_INSTRUMENTS)

    def evaluate(self, risk_input: RiskInput) -> dict[str, Any]:
        symbol = (risk_input.symbol or "").strip().upper()
        side = (risk_input.side or "").strip().upper()
        quantity = max(0, int(risk_input.quantity or 0))
        signal = dict(risk_input.signal or {})
        health = dict(risk_input.market_health or {})
        account = dict(risk_input.account_state or {})
        limits = self.config.riskLimits
        blocked: list[str] = []

        mode = self.config.tradingMode.value
        if mode == "READ_ONLY":
            blocked.append("TRADING_MODE_READ_ONLY")
        if mode == "LIVE_DISABLED":
            blocked.append("LIVE_TRADING_DISABLED_MODE")
        if mode == "LIVE_ENABLED" and not self.config.liveTradingEnabled:
            blocked.append("LIVE_ENABLED_NOT_CONFIRMED_BY_CONFIG")
        if risk_input.order_path.upper() == "LIVE":
            blocked.append("REAL_LIVE_ORDER_PATH_NOT_IMPLEMENTED")

        if not self.config.liveTradingEnabled and risk_input.order_path.upper() == "LIVE":
            blocked.append("ENABLE_LIVE_TRADING_FALSE")

        if not bool(health.get("marketOpen", False)):
            blocked.append("MARKET_CLOSED")
        if not risk_input.instrument_allowed or (self.allowed_instruments and symbol not in self.allowed_instruments):
            blocked.append("INSTRUMENT_NOT_ALLOWED")
        if not is_actionable_data_allowed(health):
            blocked.append("MARKET_DATA_NOT_ACTIONABLE")

        action = str(signal.get("action") or signal.get("decision") or "").upper()
        if side not in {"BUY", "SELL"}:
            blocked.append("SIDE_MUST_BE_BUY_OR_SELL")
        if action not in _ALLOWED_ACTIONS:
            blocked.append("SIGNAL_NOT_ACTIONABLE")
        elif action != side:
            blocked.append("ORDER_SIDE_DOES_NOT_MATCH_SIGNAL")

        confidence = _number(signal.get("confidence", signal.get("confidence_score")), 0.0)
        if confidence < float(limits.minSignalConfidence):
            blocked.append("SIGNAL_CONFIDENCE_BELOW_MINIMUM")

        stop_loss = _number_or_none(signal.get("stop_loss"))
        if stop_loss is None:
            blocked.append("STOP_LOSS_REQUIRED")

        targets = _targets(signal)
        if not targets:
            blocked.append("TARGET_REQUIRED")

        risk_reward = _number_or_none(signal.get("risk_reward"))
        if risk_reward is None:
            blocked.append("RISK_REWARD_REQUIRED")
        elif risk_reward < float(limits.minRiskReward):
            blocked.append("RISK_REWARD_BELOW_MINIMUM")

        max_qty = int(limits.maxQtyPerOrder)
        if quantity <= 0:
            blocked.append("QUANTITY_REQUIRED")
        if max_qty >= 0 and quantity > max_qty:
            blocked.append("MAX_QTY_PER_ORDER_EXCEEDED")

        open_positions = tuple(risk_input.open_positions or ())
        if len(open_positions) >= int(limits.maxOpenPositions):
            blocked.append("MAX_OPEN_POSITIONS_EXCEEDED")
        if _has_duplicate(symbol, side, open_positions) or _has_duplicate(symbol, side, tuple(risk_input.open_orders or ())) :
            blocked.append("DUPLICATE_ORDER_OR_POSITION")

        daily_loss = abs(min(0.0, _number(account.get("daily_pnl", account.get("realized_pnl")), 0.0)))
        if daily_loss >= float(limits.maxDailyLoss) > 0:
            blocked.append("MAX_DAILY_LOSS_EXCEEDED")
        if risk_input.weekly_loss >= max(float(limits.maxDailyLoss) * 5, float(limits.maxDailyLoss)) > 0:
            blocked.append("MAX_WEEKLY_LOSS_EXCEEDED")
        if risk_input.consecutive_losses >= 3:
            blocked.append("CONSECUTIVE_LOSS_LIMIT_EXCEEDED")
        if risk_input.max_drawdown >= float(limits.maxDailyLoss) > 0:
            blocked.append("MAX_DRAWDOWN_EXCEEDED")

        if risk_input.cooldown_active:
            blocked.append("COOLDOWN_ACTIVE")
        if risk_input.kill_switch_active:
            blocked.append("KILL_SWITCH_ACTIVE")
        if risk_input.order_path.upper() == "LIVE" and not risk_input.broker_connected:
            blocked.append("BROKER_NOT_CONNECTED")
        if risk_input.position_drift_detected:
            blocked.append("POSITION_DRIFT_DETECTED")

        risk_amount = _risk_amount(signal, quantity)
        position_size = quantity
        allowed = not blocked
        return {
            "allowed": allowed,
            "blocked_reasons": tuple(dict.fromkeys(blocked)),
            "mode": mode,
            "max_quantity_allowed": max_qty,
            "position_size": position_size,
            "risk_amount": risk_amount,
            "timestamp": datetime.now(UTC).isoformat(),
            "go_live_allowed": False,
        }


def check_order_risk(**kwargs: Any) -> dict[str, Any]:
    engine = RiskEngine(kwargs.pop("config", None))
    return engine.evaluate(RiskInput(**kwargs))


def _number(value: Any, default: float) -> float:
    try:
        if value in (None, "", "DATA_UNAVAILABLE"):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _number_or_none(value: Any) -> float | None:
    try:
        if value in (None, "", "DATA_UNAVAILABLE"):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _targets(signal: Mapping[str, Any]) -> tuple[float, ...]:
    raw = signal.get("targets", ())
    values: list[float] = []
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        for item in raw:
            number = _number_or_none(item)
            if number is not None:
                values.append(number)
    for key in ("target_1", "target_2", "target_3"):
        number = _number_or_none(signal.get(key))
        if number is not None:
            values.append(number)
    return tuple(dict.fromkeys(values))


def _risk_amount(signal: Mapping[str, Any], quantity: int) -> float:
    entry = _number_or_none(signal.get("entry"))
    stop = _number_or_none(signal.get("stop_loss"))
    if entry is None or stop is None or quantity <= 0:
        return 0.0
    return round(abs(entry - stop) * quantity, 2)


def _has_duplicate(symbol: str, side: str, rows: Sequence[Mapping[str, Any]]) -> bool:
    for row in rows:
        row_symbol = str(row.get("symbol") or "").upper()
        row_side = str(row.get("side") or row.get("action") or row.get("direction") or "").upper()
        if row_symbol == symbol and (not row_side or side in row_side or row_side in {"LONG", "BUY"}):
            return True
    return False
