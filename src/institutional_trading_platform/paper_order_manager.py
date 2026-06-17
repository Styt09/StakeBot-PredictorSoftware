"""Paper order manager for ALPHA-GATE X.

Phase 6 is paper-only. It simulates virtual fills and never calls broker order
placement APIs. The manager is state-container agnostic so the existing web app
can wrap its current in-memory paper account without rewriting the dashboard.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, UTC
from enum import Enum
from typing import Any, Mapping
from uuid import uuid4

DATA_UNAVAILABLE = "DATA_UNAVAILABLE"


class PaperOrderStatus(str, Enum):
    CREATED = "CREATED"
    VALIDATED = "VALIDATED"
    RISK_APPROVED = "RISK_APPROVED"
    BLOCKED = "BLOCKED"
    PAPER_FILLED = "PAPER_FILLED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


@dataclass
class PaperExecutionState:
    cash_balance: float = 100000.0
    open_positions: list[dict[str, Any]] = field(default_factory=list)
    closed_trades: list[dict[str, Any]] = field(default_factory=list)
    orders: list[dict[str, Any]] = field(default_factory=list)
    audit_log: list[dict[str, Any]] = field(default_factory=list)
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    brokerage_placeholder: float = 0.0
    slippage_placeholder: float = 0.0


class PaperOrderManager:
    def __init__(self, state: PaperExecutionState | None = None) -> None:
        self.state = state or PaperExecutionState()

    def create_order(
        self,
        *,
        symbol: str,
        side: str,
        quantity: int,
        quote: Mapping[str, Any],
        risk: Mapping[str, Any],
        stop_loss: float | None = None,
        target_1: float | None = None,
        target_2: float | None = None,
    ) -> dict[str, Any]:
        symbol = (symbol or "").strip().upper()
        side = (side or "BUY").strip().upper()
        quantity = max(0, int(quantity or 0))
        order = self._base_order(symbol, side, quantity, stop_loss, target_1, target_2)
        self.state.orders.append(order)
        self._audit("PAPER_ORDER_CREATED", order_id=order["order_id"], symbol=symbol, side=side, quantity=quantity)

        validation_error = self._validation_error(symbol, side, quantity, quote)
        if validation_error:
            return self._block(order, validation_error)

        order["status"] = PaperOrderStatus.VALIDATED.value
        if not bool(risk.get("allowed")):
            return self._block(order, "RISK_BLOCKED", tuple(risk.get("blocked_reasons") or ()))

        order["status"] = PaperOrderStatus.RISK_APPROVED.value
        ltp = _float(quote.get("ltp"), 0.0)
        if side == "BUY":
            return self._fill_buy(order, ltp)
        if side == "SELL":
            return self._fill_sell(order, ltp)
        return self._block(order, "SIDE_MUST_BE_BUY_OR_SELL")

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        for order in self.state.orders:
            if order.get("order_id") == order_id:
                if order.get("status") in {PaperOrderStatus.PAPER_FILLED.value, PaperOrderStatus.CANCELLED.value}:
                    return {"status": "BLOCKED", "reason": "ORDER_NOT_CANCELLABLE", "order": order, "go_live_allowed": False}
                order["status"] = PaperOrderStatus.CANCELLED.value
                order["updated_at"] = _now()
                self._audit("PAPER_ORDER_CANCELLED", order_id=order_id)
                return {"status": "PASS", "order": order, "go_live_allowed": False}
        return {"status": "BLOCKED", "reason": "ORDER_NOT_FOUND", "go_live_allowed": False}

    def status(self) -> dict[str, Any]:
        self.mark_to_market({})
        return {
            "cash_balance": round(self.state.cash_balance, 2),
            "open_positions": tuple(self.state.open_positions),
            "closed_trades": tuple(self.state.closed_trades),
            "orders": tuple(self.state.orders),
            "audit_log": tuple(self.state.audit_log),
            "realized_pnl": round(self.state.realized_pnl, 2),
            "unrealized_pnl": round(self.state.unrealized_pnl, 2),
            "brokerage_placeholder": self.state.brokerage_placeholder,
            "slippage_placeholder": self.state.slippage_placeholder,
            "go_live_allowed": False,
        }

    def report(self) -> dict[str, Any]:
        return {
            "orders": tuple(self.state.orders),
            "trades": tuple(self.state.closed_trades),
            "open_positions": tuple(self.state.open_positions),
            "audit_log": tuple(self.state.audit_log),
            "brokerage_placeholder": self.state.brokerage_placeholder,
            "slippage_placeholder": self.state.slippage_placeholder,
            "go_live_allowed": False,
        }

    def mark_to_market(self, quotes_by_symbol: Mapping[str, Mapping[str, Any]]) -> None:
        unrealized = 0.0
        for position in self.state.open_positions:
            quote = quotes_by_symbol.get(str(position.get("symbol", "")).upper(), {}) if quotes_by_symbol else {}
            ltp = _float(quote.get("ltp"), _float(position.get("ltp"), _float(position.get("entry_price"), 0.0)))
            position["ltp"] = ltp
            pnl = (ltp - _float(position.get("entry_price"), 0.0)) * int(position.get("quantity", 0))
            position["unrealized_pnl"] = round(pnl, 2)
            unrealized += pnl
        self.state.unrealized_pnl = round(unrealized, 2)

    def _fill_buy(self, order: dict[str, Any], ltp: float) -> dict[str, Any]:
        cost = round(ltp * int(order["quantity"]), 2)
        if cost > self.state.cash_balance:
            return self._block(order, "INSUFFICIENT_PAPER_CASH")
        if self._open_position(order["symbol"]):
            return self._block(order, "DUPLICATE_OPEN_POSITION")
        self.state.cash_balance = round(self.state.cash_balance - cost, 2)
        position = {
            "position_id": f"paper-pos-{uuid4()}",
            "symbol": order["symbol"],
            "side": "LONG",
            "quantity": int(order["quantity"]),
            "entry_price": ltp,
            "ltp": ltp,
            "stop_loss": order.get("stop_loss"),
            "target_1": order.get("target_1"),
            "target_2": order.get("target_2"),
            "unrealized_pnl": 0.0,
            "opened_at": _now(),
            "data_source": "PAPER_ORDER_MANAGER",
        }
        self.state.open_positions.append(position)
        return self._fill(order, ltp, position=position)

    def _fill_sell(self, order: dict[str, Any], ltp: float) -> dict[str, Any]:
        position = self._open_position(order["symbol"])
        if not position:
            return self._block(order, "NO_OPEN_LONG_POSITION")
        self.state.open_positions.remove(position)
        qty = int(position.get("quantity", 0))
        pnl = round((ltp - _float(position.get("entry_price"), 0.0)) * qty, 2)
        self.state.cash_balance = round(self.state.cash_balance + (ltp * qty), 2)
        self.state.realized_pnl = round(self.state.realized_pnl + pnl, 2)
        trade = {
            **position,
            "exit_price": ltp,
            "exit_reason": "MANUAL_EXIT",
            "pnl": pnl,
            "closed_at": _now(),
            "data_source": "PAPER_ORDER_MANAGER",
        }
        self.state.closed_trades.append(trade)
        return self._fill(order, ltp, trade=trade)

    def _fill(self, order: dict[str, Any], fill_price: float, **extra: Any) -> dict[str, Any]:
        order["status"] = PaperOrderStatus.PAPER_FILLED.value
        order["fill_price"] = fill_price
        order["updated_at"] = _now()
        self._audit("PAPER_ORDER_FILLED", order_id=order["order_id"], symbol=order["symbol"], fill_price=fill_price)
        return {"status": "PASS", "paper_order": order, **extra, "go_live_allowed": False}

    def _block(self, order: dict[str, Any], reason: str, blocked_reasons: tuple[str, ...] = ()) -> dict[str, Any]:
        order["status"] = PaperOrderStatus.BLOCKED.value
        order["blocked_reason"] = reason
        order["blocked_reasons"] = blocked_reasons or (reason,)
        order["updated_at"] = _now()
        self._audit("PAPER_ORDER_BLOCKED", order_id=order["order_id"], reason=reason, blocked_reasons=order["blocked_reasons"])
        return {"status": "BLOCKED", "reason": reason, "blocked_reasons": order["blocked_reasons"], "paper_order": order, "go_live_allowed": False}

    def _base_order(self, symbol: str, side: str, quantity: int, stop_loss: float | None, target_1: float | None, target_2: float | None) -> dict[str, Any]:
        now = _now()
        return {
            "order_id": f"paper-{uuid4()}",
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "status": PaperOrderStatus.CREATED.value,
            "stop_loss": stop_loss,
            "target_1": target_1,
            "target_2": target_2,
            "created_at": now,
            "updated_at": now,
            "brokerage_placeholder": self.state.brokerage_placeholder,
            "slippage_placeholder": self.state.slippage_placeholder,
            "go_live_allowed": False,
        }

    def _validation_error(self, symbol: str, side: str, quantity: int, quote: Mapping[str, Any]) -> str | None:
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
