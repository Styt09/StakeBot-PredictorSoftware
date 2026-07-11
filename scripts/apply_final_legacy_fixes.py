"""Apply deterministic compatibility fixes to legacy UI/runtime files.

This script is idempotent and is used only to repair already-committed legacy
contracts while the new paper_web_app remains the clean deployment entry.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(text: str, pattern: str, replacement: str, label: str) -> str:
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
    if count != 1:
        raise RuntimeError(f"Could not patch {label}; matches={count}")
    return updated


def patch_web_app() -> None:
    path = ROOT / "src/institutional_trading_platform/web_app.py"
    text = path.read_text()

    text = replace_once(
        text,
        r"def _paper_order\(payload: Mapping\[str, Any\]\) -> dict\[str, Any\]:.*?\n\ndef _paper_position_close",
        '''def _paper_order(payload: Mapping[str, Any]) -> dict[str, Any]:
    symbol = str(payload.get("symbol", "RELIANCE")).strip().upper()
    side = str(payload.get("side", "BUY")).strip().upper()
    quantity = _safe_int(payload.get("quantity"), 0)
    if quantity <= 0:
        return {"status": "BLOCKED", "reason": "quantity must be positive", "go_live_allowed": False}
    price, source = _paper_execution_price(symbol, payload)
    if price <= 0:
        return {"status": "BLOCKED", "reason": "validated quote unavailable and entry_price missing", "go_live_allowed": False}
    if side == "BUY":
        return _paper_open_long(symbol, quantity, price, payload, source, event="PAPER_BUY")
    if side == "SELL":
        open_long = next((p for p in _PAPER.get("open_positions", []) if p["symbol"] == symbol and p["side"] == "BUY"), None)
        if open_long is None:
            return {"status": "BLOCKED", "reason": "SELL opens short only when explicitly supported; no matching long paper position found", "go_live_allowed": False}
        open_quantity = int(open_long["quantity"])
        if quantity > open_quantity:
            return {"status": "BLOCKED", "reason": "SELL_QUANTITY_EXCEEDS_OPEN_LONG", "requested_quantity": quantity, "open_quantity": open_quantity, "go_live_allowed": False}
        if quantity < open_quantity:
            return _paper_partial_close_long(open_long["position_id"], quantity, price, "MANUAL_PARTIAL_EXIT", source)
        return _paper_close_position(open_long["position_id"], price, "MANUAL_EXIT", source)
    return {"status": "BLOCKED", "reason": "side must be BUY or SELL", "go_live_allowed": False}


def _paper_partial_close_long(position_id: str, quantity: int, exit_price: float, exit_reason: str, source: str) -> dict[str, Any]:
    position = _paper_find_position(position_id)
    if position is None:
        return {"status": "BLOCKED", "reason": "position_id not found", "go_live_allowed": False}
    open_quantity = int(position["quantity"])
    if quantity <= 0 or quantity >= open_quantity:
        return {"status": "BLOCKED", "reason": "partial quantity must be between 1 and open quantity - 1", "go_live_allowed": False}
    entry = float(position["entry_price"])
    pnl = round((exit_price - entry) * quantity, 2)
    proceeds = round(exit_price * quantity, 2)
    remaining = open_quantity - quantity
    _PAPER["cash_balance"] = round(float(_PAPER.get("cash_balance", 0.0)) + proceeds, 2)
    position["quantity"] = remaining
    position["last_price"] = round(exit_price, 2)
    position["unrealized_pnl"] = round((exit_price - entry) * remaining, 2)
    partial_trade = {
        "position_id": position_id,
        "symbol": position["symbol"],
        "side": position["side"],
        "quantity": quantity,
        "entry_price": round(entry, 2),
        "exit_price": round(exit_price, 2),
        "exit_reason": exit_reason,
        "opened_at": position.get("opened_at"),
        "closed_at": _now(),
        "pnl": pnl,
        "data_source": source,
        "status": "PARTIALLY_CLOSED",
        "go_live_allowed": False,
    }
    _PAPER.setdefault("closed_trades", []).append(partial_trade)
    _paper_ledger(exit_reason, f"Partially closed virtual {position['symbol']} x{quantity} @ {exit_price:.2f}; P&L {pnl:.2f}", position_id=position_id, symbol=position["symbol"], quantity=quantity, pnl=pnl)
    return {"status": "PASS", "partial_trade": partial_trade, "paper_order": position, "paper_status": _paper_status(), "go_live_allowed": False}


def _paper_position_close''',
        "legacy paper order and partial close",
    )

    text = replace_once(
        text,
        r"def _paper_open_long\(symbol: str, quantity: int, price: float, payload: Mapping\[str, Any\], source: str, \*, event: str\) -> dict\[str, Any\]:.*?\n\ndef _paper_close_position",
        '''def _paper_open_long(symbol: str, quantity: int, price: float, payload: Mapping[str, Any], source: str, *, event: str) -> dict[str, Any]:
    cost = round(price * quantity, 2)
    if float(_PAPER.get("cash_balance", 0.0)) < cost:
        return {"status": "BLOCKED", "reason": "INSUFFICIENT_PAPER_BALANCE", "required_cash": cost, "cash_balance": _PAPER.get("cash_balance", 0.0), "go_live_allowed": False}

    existing = next((p for p in _PAPER.get("open_positions", []) if p["symbol"] == symbol and p["side"] == "BUY"), None)
    _PAPER["cash_balance"] = round(float(_PAPER.get("cash_balance", 0.0)) - cost, 2)

    if existing is not None:
        old_quantity = int(existing["quantity"])
        old_entry = float(existing["entry_price"])
        new_quantity = old_quantity + quantity
        average_price = round(((old_entry * old_quantity) + (price * quantity)) / new_quantity, 2)
        existing["quantity"] = new_quantity
        existing["entry_price"] = average_price
        existing["last_price"] = round(price, 2)
        existing["lot_count"] = int(existing.get("lot_count", 1)) + 1
        existing["unrealized_pnl"] = round((price - average_price) * new_quantity, 2)
        for key in ("stop_loss", "target_1", "target_2"):
            value = _safe_float(payload.get(key), 0.0)
            if value > 0:
                existing[key] = round(value, 2)
        _paper_ledger("PAPER_BUY_SCALE_IN", f"Added virtual BUY lot {quantity} {symbol} @ {price:.2f}; average {average_price:.2f}", position_id=existing["position_id"], symbol=symbol, quantity=quantity, price=price, average_price=average_price)
        return {"status": "PASS", "paper_order": existing, "paper_status": _paper_status(), "go_live_allowed": False}

    position = {
        "position_id": f"paper-{uuid4()}",
        "symbol": symbol,
        "side": "BUY",
        "quantity": quantity,
        "entry_price": round(price, 2),
        "stop_loss": round(_safe_float(payload.get("stop_loss"), 0.0), 2),
        "target_1": round(_safe_float(payload.get("target_1"), 0.0), 2),
        "target_2": round(_safe_float(payload.get("target_2"), 0.0), 2),
        "opened_at": _now(),
        "data_source": source,
        "status": "OPEN",
        "last_price": round(price, 2),
        "unrealized_pnl": 0.0,
        "lot_count": 1,
        "go_live_allowed": False,
    }
    _PAPER.setdefault("open_positions", []).append(position)
    _paper_ledger(event, f"Opened virtual BUY {quantity} {symbol} @ {price:.2f}", position_id=position["position_id"], symbol=symbol, quantity=quantity, price=price)
    return {"status": "PASS", "paper_order": position, "paper_status": _paper_status(), "go_live_allowed": False}


def _paper_close_position''',
        "legacy paper scale-in",
    )

    text = replace_once(
        text,
        r"def _paper_execution_price\(symbol: str, payload: Mapping\[str, Any\]\) -> tuple\[float, str\]:.*?\n\ndef _paper_find_position",
        '''def _paper_execution_price(symbol: str, payload: Mapping[str, Any]) -> tuple[float, str]:
    entered = _safe_float(payload.get("limit_price") or payload.get("entry_price") or payload.get("price"), 0.0)
    if entered > 0:
        return entered, "USER_ENTERED_PAPER_PRICE"
    quote = _LAST_QUOTES.get(symbol)
    if quote and quote.get("validation_status") == "VALIDATED" and isinstance(quote.get("ltp"), (int, float)):
        return float(quote["ltp"]), "ZERODHA_KITE_QUOTE" if quote.get("data_source") != "TEST_QUOTE" else "TEST_QUOTE"
    return 0.0, DATA_UNAVAILABLE


def _paper_find_position''',
        "typed paper price priority",
    )

    duplicate_line = '    if any(p["symbol"] == symbol and p["side"] == "BUY" for p in _PAPER.get("open_positions", [])): reasons.append("DUPLICATE_OPEN_POSITION")'
    replacement = '    if any(p["symbol"] == symbol and p["side"] == "BUY" for p in _PAPER.get("open_positions", [])):\n        reasons.append("AUTO_SCALE_IN_OFF")\n        reasons.append("DUPLICATE_OPEN_POSITION")'
    if duplicate_line not in text:
        raise RuntimeError("Could not patch AUTO_SCALE_IN_OFF")
    text = text.replace(duplicate_line, replacement, 1)

    old_return = '    return {"state": state, "selected_symbol": symbol, "latest_ltp": round(entry, 2) if entry else DATA_UNAVAILABLE,'
    new_return = '    return {"requested": bool(settings["paper_auto_trade_enabled"]), "state": state, "selected_symbol": symbol, "latest_ltp": round(entry, 2) if entry else DATA_UNAVAILABLE,'
    if old_return not in text:
        raise RuntimeError("Could not patch paper auto requested flag")
    text = text.replace(old_return, new_return, 1)

    path.write_text(text)


def patch_market_data_provider() -> None:
    path = ROOT / "src/institutional_trading_platform/market_data_safety.py"
    text = path.read_text()
    text = replace_once(
        text,
        r"class ExistingDataProvider:.*?\n\nclass MarketDataHealthService:",
        '''class ExistingDataProvider:
    def __init__(self, quote_fetcher: Callable[[str], Mapping[str, Any]], history_fetcher: Callable[..., Mapping[str, Any]]) -> None:
        self._quote_fetcher = quote_fetcher
        self._history_fetcher = history_fetcher

    def quote(self, symbol: str) -> Mapping[str, Any]:
        normalized = (symbol or "RELIANCE").strip().upper()
        payload = dict(self._quote_fetcher(normalized) or {})
        payload.setdefault("symbol", normalized)
        payload.setdefault("go_live_allowed", False)
        return payload

    def history(self, symbol: str, interval: str = "5minute") -> Mapping[str, Any]:
        normalized = (symbol or "RELIANCE").strip().upper()
        payload = dict(self._history_fetcher(normalized, interval=interval) or {})
        payload.setdefault("symbol", normalized)
        payload.setdefault("interval", interval)
        payload.setdefault("go_live_allowed", False)
        return payload


class MarketDataHealthService:''',
        "existing data provider normalization",
    )
    path.write_text(text)


def patch_premium_dashboard() -> None:
    path = ROOT / "src/institutional_trading_platform/premium_dashboard.py"
    text = path.read_text()
    needle = "Real Zerodha orders remain blocked. This UI is frontend-only and uses PAPER / SHADOW validation. No real-order control is provided."
    replacement = needle + " Read-only broker access only."
    if replacement not in text:
        if needle not in text:
            raise RuntimeError("Could not patch premium dashboard broker wording")
        text = text.replace(needle, replacement, 1)
    path.write_text(text)


def main() -> None:
    patch_web_app()
    patch_market_data_provider()
    patch_premium_dashboard()
    print("Applied final legacy compatibility fixes")


if __name__ == "__main__":
    main()
