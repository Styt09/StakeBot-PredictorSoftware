"""Shadow trading layer for ALPHA-GATE X.

Phase 7 is theoretical-only. It observes live market data, evaluates safe
signals and risk output supplied by the web layer, and records simulated shadow
orders. It never calls a broker mutation API and never enables real-money
trading.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Mapping
from uuid import uuid4

DATA_UNAVAILABLE = "DATA_UNAVAILABLE"


class ShadowOrderStatus(str, Enum):
    SHADOW_CREATED = "SHADOW_CREATED"
    SHADOW_VALIDATED = "SHADOW_VALIDATED"
    SHADOW_RISK_APPROVED = "SHADOW_RISK_APPROVED"
    SHADOW_BLOCKED = "SHADOW_BLOCKED"
    SHADOW_FILLED_THEORETICAL = "SHADOW_FILLED_THEORETICAL"
    SHADOW_CANCELLED = "SHADOW_CANCELLED"
    SHADOW_FAILED = "SHADOW_FAILED"


@dataclass
class ShadowTradingState:
    open_positions: list[dict[str, Any]] = field(default_factory=list)
    closed_trades: list[dict[str, Any]] = field(default_factory=list)
    orders: list[dict[str, Any]] = field(default_factory=list)
    audit_log: list[dict[str, Any]] = field(default_factory=list)
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    brokerage_placeholder: float = 0.0
    slippage_placeholder: float = 0.0
    drift_placeholder: str = "NOT_IMPLEMENTED"
    accuracy_report_placeholder: str = "NOT_IMPLEMENTED"


class ShadowTradingEngine:
    def __init__(self, state: ShadowTradingState | None = None) -> None:
        self.state = state or ShadowTradingState()

    def evaluate_order(
        self,
        *,
        symbol: str,
        side: str,
        quantity: int,
        quote: Mapping[str, Any],
        safe_signal: Mapping[str, Any],
        risk: Mapping[str, Any],
    ) -> dict[str, Any]:
        symbol = (symbol or "").strip().upper()
        side = (side or "BUY").strip().upper()
        quantity = max(0, int(quantity or 0))
        order = self._base_order(symbol, side, quantity, safe_signal)
        self.state.orders.append(order)
        self._audit("SHADOW_ORDER_CREATED", order_id=order["order_id"], symbol=symbol, side=side, quantity=quantity)

        validation_error = self._validation_error(symbol, side, quantity, quote, safe_signal)
        if validation_error:
            return self._block(order, validation_error)

        order["status"] = ShadowOrderStatus.SHADOW_VALIDATED.value
        if not bool(risk.get("allowed")):
            return self._block(order, "SHADOW_RISK_BLOCKED", tuple(risk.get("blocked_reasons") or ()))

        order["status"] = ShadowOrderStatus.SHADOW_RISK_APPROVED.value
        ltp = _float(quote.get("ltp"), 0.0)
        if side == "BUY":
            return self._fill_buy(order, ltp)
        if side == "SELL":
            return self._fill_sell(order, ltp)
        return self._block(order, "SIDE_MUST_BE_BUY_OR_SELL")

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        for order in self.state.orders:
            if order.get("order_id") == order_id:
                if order.get("status") in {
                    ShadowOrderStatus.SHADOW_FILLED_THEORETICAL.value,
                    ShadowOrderStatus.SHADOW_CANCELLED.value,
                }:
                    return {"status": "SHADOW_BLOCKED", "reason": "SHADOW_ORDER_NOT_CANCELLABLE", "order": order, "go_live_allowed": False}
                order["status"] = ShadowOrderStatus.SHADOW_CANCELLED.value
                order["updated_at"] = _now()
                self._audit("SHADOW_ORDER_CANCELLED", order_id=order_id)
                return {"status": "PASS", "shadow_order": order, "go_live_allowed": False}
        return {"status": "SHADOW_BLOCKED", "reason": "SHADOW_ORDER_NOT_FOUND", "go_live_allowed": False}

    def reset(self) -> dict[str, Any]:
        self.state.open_positions.clear()
        self.state.closed_trades.clear()
        self.state.orders.clear()
        self.state.realized_pnl = 0.0
        self.state.unrealized_pnl = 0.0
        self._audit("SHADOW_RESET")
        return {"status": "PASS", "go_live_allowed": False}

    def status(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "mode": "SHADOW_THEORETICAL_ONLY",
            "open_positions": tuple(self.state.open_positions),
            "orders": tuple(self.state.orders),
            "trades": tuple(self.state.closed_trades),
            "realized_pnl": round(self.state.realized_pnl, 2),
            "unrealized_pnl": round(self.state.unrealized_pnl, 2),
            "brokerage_placeholder": self.state.brokerage_placeholder,
            "slippage_placeholder": self.state.slippage_placeholder,
            "go_live_allowed": False,
        }

    def report(self) -> dict[str, Any]:
        return {
            **self.status(),
            "audit_log": tuple(self.state.audit_log),
            "drift_placeholder": self.state.drift_placeholder,
            "accuracy_report_placeholder": self.state.accuracy_report_placeholder,
            "summary": {
                "orders": len(self.state.orders),
                "trades": len(self.state.closed_trades),
                "open_positions": len(self.state.open_positions),
                "realized_pnl": round(self.state.realized_pnl, 2),
                "unrealized_pnl": round(self.state.unrealized_pnl, 2),
            },
            "go_live_allowed": False,
        }

    def mark_to_market(self, quotes_by_symbol: Mapping[str, Mapping[str, Any]]) -> None:
        total = 0.0
        for position in self.state.open_positions:
            symbol = str(position.get("symbol", "")).upper()
            quote = quotes_by_symbol.get(symbol, {}) if quotes_by_symbol else {}
            ltp = _float(quote.get("ltp"), _float(position.get("ltp"), _float(position.get("entry_price"), 0.0)))
            position["ltp"] = ltp
            pnl = (ltp - _float(position.get("entry_price"), 0.0)) * int(position.get("quantity", 0))
            position["unrealized_pnl"] = round(pnl, 2)
            total += pnl
        self.state.unrealized_pnl = round(total, 2)

    def _fill_buy(self, order: dict[str, Any], ltp: float) -> dict[str, Any]:
        if self._open_position(order["symbol"]):
            return self._block(order, "SHADOW_DUPLICATE_OPEN_POSITION")
        position = {
            "position_id": f"shadow-pos-{uuid4()}",
            "symbol": order["symbol"],
            "side": "LONG",
            "quantity": int(order["quantity"]),
            "entry_price": ltp,
            "ltp": ltp,
            "unrealized_pnl": 0.0,
            "opened_at": _now(),
            "theoretical_only": True,
            "go_live_allowed": False,
        }
        self.state.open_positions.append(position)
        return self._fill(order, ltp, position=position)

    def _fill_sell(self, order: dict[str, Any], ltp: float) -> dict[str, Any]:
        position = self._open_position(order["symbol"])
        if not position:
            return self._block(order, "NO_OPEN_SHADOW_LONG_POSITION")
        self.state.open_positions.remove(position)
        qty = int(position.get("quantity", 0))
        pnl = round((ltp - _float(position.get("entry_price"), 0.0)) * qty, 2)
        self.state.realized_pnl = round(self.state.realized_pnl + pnl, 2)
        trade = {
            **position,
            "exit_price": ltp,
            "exit_reason": "SHADOW_EXIT",
            "pnl": pnl,
            "closed_at": _now(),
            "theoretical_only": True,
            "go_live_allowed": False,
        }
        self.state.closed_trades.append(trade)
        return self._fill(order, ltp, trade=trade)

    def _fill(self, order: dict[str, Any], fill_price: float, **extra: Any) -> dict[str, Any]:
        order["status"] = ShadowOrderStatus.SHADOW_FILLED_THEORETICAL.value
        order["fill_price"] = fill_price
        order["updated_at"] = _now()
        self._audit("SHADOW_ORDER_FILLED_THEORETICAL", order_id=order["order_id"], symbol=order["symbol"], fill_price=fill_price)
        return {"status": "PASS", "shadow_order": order, **extra, "go_live_allowed": False}

    def _block(self, order: dict[str, Any], reason: str, blocked_reasons: tuple[str, ...] = ()) -> dict[str, Any]:
        order["status"] = ShadowOrderStatus.SHADOW_BLOCKED.value
        order["blocked_reason"] = reason
        order["blocked_reasons"] = blocked_reasons or (reason,)
        order["updated_at"] = _now()
        self._audit("SHADOW_ORDER_BLOCKED", order_id=order["order_id"], reason=reason, blocked_reasons=order["blocked_reasons"])
        return {"status": "SHADOW_BLOCKED", "reason": reason, "blocked_reasons": order["blocked_reasons"], "shadow_order": order, "go_live_allowed": False}

    def _base_order(self, symbol: str, side: str, quantity: int, safe_signal: Mapping[str, Any]) -> dict[str, Any]:
        now = _now()
        return {
            "order_id": f"shadow-{uuid4()}",
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "status": ShadowOrderStatus.SHADOW_CREATED.value,
            "signal_action": safe_signal.get("action"),
            "confidence": safe_signal.get("confidence"),
            "created_at": now,
            "updated_at": now,
            "theoretical_only": True,
            "brokerage_placeholder": self.state.brokerage_placeholder,
            "slippage_placeholder": self.state.slippage_placeholder,
            "go_live_allowed": False,
        }

    def _validation_error(self, symbol: str, side: str, quantity: int, quote: Mapping[str, Any], safe_signal: Mapping[str, Any]) -> str | None:
        if not symbol:
            return "SYMBOL_REQUIRED"
        if side not in {"BUY", "SELL"}:
            return "SIDE_MUST_BE_BUY_OR_SELL"
        if quantity < 1:
            return "QUANTITY_REQUIRED"
        if quote.get("validation_status") != "VALIDATED":
            return "VALIDATED_QUOTE_REQUIRED"
        if _float(quote.get("ltp"), 0.0) <= 0:
            return "VALID_LTP_REQUIRED"
        action = str(safe_signal.get("action") or "").upper()
        if action in {"", "NO_TRADE", "HOLD", DATA_UNAVAILABLE}:
            return "SHADOW_SIGNAL_NOT_ACTIONABLE"
        return None

    def _open_position(self, symbol: str) -> dict[str, Any] | None:
        normalized = symbol.upper()
        for position in self.state.open_positions:
            if str(position.get("symbol", "")).upper() == normalized:
                return position
        return None

    def _audit(self, event: str, **fields: Any) -> None:
        self.state.audit_log.append({"event": event, "timestamp": _now(), **fields, "go_live_allowed": False})


def _float(value: Any, default: float) -> float:
    try:
        if value in (None, "", DATA_UNAVAILABLE):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _now() -> str:
    return datetime.now(UTC).isoformat()
