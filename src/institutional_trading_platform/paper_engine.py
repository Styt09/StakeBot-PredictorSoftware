"""Persistent, paper-only trading engine.

This module never calls broker order APIs. All orders are virtual and are stored
in SQLite so balances and positions survive process restarts.
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator, Mapping
from uuid import uuid4

DATA_UNAVAILABLE = "DATA_UNAVAILABLE"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _integer(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class PaperEngine:
    """Thread-safe SQLite paper account with long and MIS-short support."""

    def __init__(self, database_path: str | Path, *, starting_balance: float = 100_000.0) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.starting_balance = float(starting_balance)
        self._lock = threading.RLock()
        self._initialize()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=30, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA foreign_keys=ON")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._lock, self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS paper_account (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    starting_balance REAL NOT NULL,
                    cash_balance REAL NOT NULL,
                    realized_pnl REAL NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS paper_positions (
                    position_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
                    quantity INTEGER NOT NULL,
                    lots INTEGER NOT NULL,
                    lot_size INTEGER NOT NULL,
                    product TEXT NOT NULL CHECK (product IN ('MIS', 'CNC')),
                    order_type TEXT NOT NULL CHECK (order_type IN ('LIMIT', 'MARKET')),
                    entry_price REAL NOT NULL,
                    last_price REAL NOT NULL,
                    margin_reserved REAL NOT NULL,
                    stop_loss REAL NOT NULL DEFAULT 0,
                    target_1 REAL NOT NULL DEFAULT 0,
                    target_2 REAL NOT NULL DEFAULT 0,
                    opened_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'OPEN'
                );

                CREATE TABLE IF NOT EXISTS paper_trades (
                    trade_id TEXT PRIMARY KEY,
                    position_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    product TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    exit_price REAL NOT NULL,
                    pnl REAL NOT NULL,
                    exit_reason TEXT NOT NULL,
                    opened_at TEXT NOT NULL,
                    closed_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS paper_ledger (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event TEXT NOT NULL,
                    message TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    payload TEXT NOT NULL DEFAULT '{}'
                );
                """
            )
            row = connection.execute("SELECT id FROM paper_account WHERE id = 1").fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO paper_account(id, starting_balance, cash_balance, realized_pnl, updated_at) VALUES (1, ?, ?, 0, ?)",
                    (self.starting_balance, self.starting_balance, _now()),
                )
                self._ledger(connection, "ACCOUNT_CREATED", f"Paper account created with {self.starting_balance:.2f}")

    @staticmethod
    def _ledger(connection: sqlite3.Connection, event: str, message: str, payload: str = "{}") -> None:
        connection.execute(
            "INSERT INTO paper_ledger(event, message, timestamp, payload) VALUES (?, ?, ?, ?)",
            (event, message, _now(), payload),
        )

    @staticmethod
    def _position_dict(row: sqlite3.Row) -> dict[str, Any]:
        payload = dict(row)
        payload.update(
            {
                "real_order": False,
                "go_live_allowed": False,
                "data_source": "SQLITE_PAPER_ENGINE",
            }
        )
        return payload

    def reset(self, starting_balance: float | None = None) -> dict[str, Any]:
        balance = _number(starting_balance, self.starting_balance)
        if balance <= 0:
            return self._blocked("STARTING_BALANCE_MUST_BE_POSITIVE")
        with self._lock, self._connection() as connection:
            connection.execute("DELETE FROM paper_positions")
            connection.execute("DELETE FROM paper_trades")
            connection.execute("DELETE FROM paper_ledger")
            connection.execute(
                "UPDATE paper_account SET starting_balance = ?, cash_balance = ?, realized_pnl = 0, updated_at = ? WHERE id = 1",
                (balance, balance, _now()),
            )
            self._ledger(connection, "ACCOUNT_RESET", f"Paper account reset to {balance:.2f}")
        return {"status": "PASS", "message": "Paper account reset", "paper_status": self.status(), "real_order": False, "go_live_allowed": False}

    def add_balance(self, amount: float) -> dict[str, Any]:
        value = _number(amount)
        if value <= 0:
            return self._blocked("AMOUNT_MUST_BE_POSITIVE")
        with self._lock, self._connection() as connection:
            connection.execute(
                "UPDATE paper_account SET starting_balance = starting_balance + ?, cash_balance = cash_balance + ?, updated_at = ? WHERE id = 1",
                (value, value, _now()),
            )
            self._ledger(connection, "BALANCE_ADD", f"Added virtual paper balance {value:.2f}")
        return {"status": "PASS", "message": "Virtual balance added", "paper_status": self.status(), "real_order": False, "go_live_allowed": False}

    def place_order(self, payload: Mapping[str, Any], *, market_price: float | None = None) -> dict[str, Any]:
        symbol = str(payload.get("symbol") or "").strip().upper()
        side = str(payload.get("side") or "BUY").strip().upper()
        product = str(payload.get("product") or "MIS").strip().upper()
        order_type = str(payload.get("order_type") or "LIMIT").strip().upper()
        lots = max(1, _integer(payload.get("lots"), 1))
        lot_size = max(1, _integer(payload.get("lot_size"), 1))
        quantity = _integer(payload.get("quantity"), lots * lot_size)
        quantity = quantity if quantity > 0 else lots * lot_size

        if not symbol:
            return self._blocked("SYMBOL_REQUIRED")
        if side not in {"BUY", "SELL"}:
            return self._blocked("SIDE_MUST_BE_BUY_OR_SELL")
        if product not in {"MIS", "CNC"}:
            return self._blocked("PRODUCT_MUST_BE_MIS_OR_CNC")
        if order_type not in {"LIMIT", "MARKET"}:
            return self._blocked("ORDER_TYPE_MUST_BE_LIMIT_OR_MARKET")
        if quantity <= 0:
            return self._blocked("QUANTITY_MUST_BE_POSITIVE")

        if order_type == "LIMIT":
            price = _number(payload.get("limit_price") or payload.get("entry_price") or payload.get("price"))
            source = "USER_LIMIT_PRICE"
            if price <= 0:
                return self._blocked("LIMIT_PRICE_REQUIRED")
        else:
            price = _number(market_price)
            source = "VALIDATED_MARKET_QUOTE"
            if price <= 0:
                return self._blocked("MARKET_PRICE_UNAVAILABLE")

        with self._lock, self._connection() as connection:
            opposite = connection.execute(
                "SELECT * FROM paper_positions WHERE symbol = ? AND side != ? AND status = 'OPEN' ORDER BY opened_at LIMIT 1",
                (symbol, side),
            ).fetchone()
            if opposite is not None:
                return self._close_row(connection, opposite, price, f"{side}_CLOSE_OPPOSITE")

            if side == "SELL" and product == "CNC":
                return self._blocked("CNC_SHORT_NOT_ALLOWED", hint="Use MIS for a new short position, or SELL an existing long position.")

            account = connection.execute("SELECT * FROM paper_account WHERE id = 1").fetchone()
            assert account is not None
            turnover = round(price * quantity, 2)
            margin_factor = 0.20 if product == "MIS" else 1.0
            margin_required = round(turnover * margin_factor, 2)
            cash = float(account["cash_balance"])
            if cash < margin_required:
                return self._blocked(
                    "INSUFFICIENT_PAPER_MARGIN",
                    required_margin=margin_required,
                    cash_balance=round(cash, 2),
                    hint="Reduce lots/quantity, select MIS, or add virtual balance.",
                )

            position_id = f"paper-{uuid4()}"
            opened_at = _now()
            position = {
                "position_id": position_id,
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
                "lots": lots,
                "lot_size": lot_size,
                "product": product,
                "order_type": order_type,
                "entry_price": round(price, 2),
                "last_price": round(price, 2),
                "margin_reserved": margin_required,
                "stop_loss": round(_number(payload.get("stop_loss")), 2),
                "target_1": round(_number(payload.get("target_1")), 2),
                "target_2": round(_number(payload.get("target_2")), 2),
                "opened_at": opened_at,
                "status": "OPEN",
            }
            connection.execute(
                """
                INSERT INTO paper_positions(
                    position_id, symbol, side, quantity, lots, lot_size, product,
                    order_type, entry_price, last_price, margin_reserved,
                    stop_loss, target_1, target_2, opened_at, status
                ) VALUES (
                    :position_id, :symbol, :side, :quantity, :lots, :lot_size, :product,
                    :order_type, :entry_price, :last_price, :margin_reserved,
                    :stop_loss, :target_1, :target_2, :opened_at, :status
                )
                """,
                position,
            )
            connection.execute(
                "UPDATE paper_account SET cash_balance = cash_balance - ?, updated_at = ? WHERE id = 1",
                (margin_required, _now()),
            )
            self._ledger(connection, f"PAPER_{side}", f"Opened virtual {side} {quantity} {symbol} @ {price:.2f}")
            position.update({"price_source": source, "real_order": False, "go_live_allowed": False, "data_source": "SQLITE_PAPER_ENGINE"})
            response = {
                "status": "PASS",
                "message": f"Paper {side} order placed",
                "paper_order": position,
                "real_order": False,
                "go_live_allowed": False,
            }
        response["paper_status"] = self.status()
        return response

    def close_position(self, position_id: str, exit_price: float, *, reason: str = "MANUAL_EXIT") -> dict[str, Any]:
        price = _number(exit_price)
        if not str(position_id).strip():
            return self._blocked("POSITION_ID_REQUIRED")
        if price <= 0:
            return self._blocked("EXIT_PRICE_REQUIRED")
        with self._lock, self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM paper_positions WHERE position_id = ? AND status = 'OPEN'",
                (str(position_id).strip(),),
            ).fetchone()
            if row is None:
                return self._blocked("POSITION_NOT_FOUND")
            return self._close_row(connection, row, price, reason)

    def _close_row(self, connection: sqlite3.Connection, row: sqlite3.Row, exit_price: float, reason: str) -> dict[str, Any]:
        quantity = int(row["quantity"])
        entry = float(row["entry_price"])
        side = str(row["side"])
        pnl = round((exit_price - entry) * quantity, 2) if side == "BUY" else round((entry - exit_price) * quantity, 2)
        release = round(float(row["margin_reserved"]) + pnl, 2)
        connection.execute("DELETE FROM paper_positions WHERE position_id = ?", (row["position_id"],))
        connection.execute(
            "UPDATE paper_account SET cash_balance = cash_balance + ?, realized_pnl = realized_pnl + ?, updated_at = ? WHERE id = 1",
            (release, pnl, _now()),
        )
        trade_id = f"trade-{uuid4()}"
        closed_at = _now()
        connection.execute(
            """
            INSERT INTO paper_trades(
                trade_id, position_id, symbol, side, quantity, product,
                entry_price, exit_price, pnl, exit_reason, opened_at, closed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trade_id,
                row["position_id"],
                row["symbol"],
                side,
                quantity,
                row["product"],
                entry,
                round(exit_price, 2),
                pnl,
                reason,
                row["opened_at"],
                closed_at,
            ),
        )
        self._ledger(connection, reason, f"Closed virtual {row['symbol']} @ {exit_price:.2f}; P&L {pnl:.2f}")
        trade = {
            "trade_id": trade_id,
            "position_id": row["position_id"],
            "symbol": row["symbol"],
            "side": side,
            "quantity": quantity,
            "product": row["product"],
            "entry_price": entry,
            "exit_price": round(exit_price, 2),
            "pnl": pnl,
            "exit_reason": reason,
            "opened_at": row["opened_at"],
            "closed_at": closed_at,
            "real_order": False,
            "go_live_allowed": False,
            "data_source": "SQLITE_PAPER_ENGINE",
        }
        return {
            "status": "PASS",
            "message": "Paper position closed",
            "closed_trade": trade,
            "real_order": False,
            "go_live_allowed": False,
        }

    def mark_price(self, symbol: str, price: float) -> dict[str, Any]:
        normalized = str(symbol).strip().upper()
        value = _number(price)
        if not normalized or value <= 0:
            return self._blocked("VALID_SYMBOL_AND_PRICE_REQUIRED")
        closed: list[dict[str, Any]] = []
        with self._lock, self._connection() as connection:
            connection.execute(
                "UPDATE paper_positions SET last_price = ? WHERE symbol = ? AND status = 'OPEN'",
                (value, normalized),
            )
            rows = connection.execute(
                "SELECT * FROM paper_positions WHERE symbol = ? AND status = 'OPEN'",
                (normalized,),
            ).fetchall()
            for row in rows:
                side = str(row["side"])
                stop = float(row["stop_loss"] or 0)
                target_1 = float(row["target_1"] or 0)
                target_2 = float(row["target_2"] or 0)
                reason = ""
                if side == "BUY":
                    if stop > 0 and value <= stop:
                        reason = "STOP_LOSS_HIT"
                    elif target_2 > 0 and value >= target_2:
                        reason = "TARGET_2_HIT"
                    elif target_1 > 0 and value >= target_1:
                        reason = "TARGET_1_HIT"
                else:
                    if stop > 0 and value >= stop:
                        reason = "STOP_LOSS_HIT"
                    elif target_2 > 0 and value <= target_2:
                        reason = "TARGET_2_HIT"
                    elif target_1 > 0 and value <= target_1:
                        reason = "TARGET_1_HIT"
                if reason:
                    closed.append(self._close_row(connection, row, value, reason)["closed_trade"])
        return {"status": "PASS", "marked_symbol": normalized, "last_price": value, "auto_closed": closed, "real_order": False, "go_live_allowed": False}

    def status(self) -> dict[str, Any]:
        with self._lock, self._connection() as connection:
            account = connection.execute("SELECT * FROM paper_account WHERE id = 1").fetchone()
            assert account is not None
            positions = [self._position_dict(row) for row in connection.execute("SELECT * FROM paper_positions WHERE status = 'OPEN' ORDER BY opened_at").fetchall()]
            trades = [dict(row) | {"real_order": False, "go_live_allowed": False, "data_source": "SQLITE_PAPER_ENGINE"} for row in connection.execute("SELECT * FROM paper_trades ORDER BY closed_at DESC LIMIT 100").fetchall()]
            ledger = [dict(row) for row in connection.execute("SELECT event, message, timestamp, payload FROM paper_ledger ORDER BY id DESC LIMIT 100").fetchall()]

        unrealized = 0.0
        reserved = 0.0
        for position in positions:
            entry = float(position["entry_price"])
            last = float(position["last_price"])
            quantity = int(position["quantity"])
            position["unrealized_pnl"] = round((last - entry) * quantity, 2) if position["side"] == "BUY" else round((entry - last) * quantity, 2)
            unrealized += float(position["unrealized_pnl"])
            reserved += float(position["margin_reserved"])

        cash = float(account["cash_balance"])
        equity = round(cash + reserved + unrealized, 2)
        wins = sum(1 for trade in trades if float(trade["pnl"]) > 0)
        losses = sum(1 for trade in trades if float(trade["pnl"]) <= 0)
        total = wins + losses
        return {
            "account_summary": {
                "mode": "PAPER_TRADING_ONLY",
                "starting_balance": round(float(account["starting_balance"]), 2),
                "cash_balance": round(cash, 2),
                "reserved_margin": round(reserved, 2),
                "equity": equity,
                "realized_pnl": round(float(account["realized_pnl"]), 2),
                "unrealized_pnl": round(unrealized, 2),
                "open_position_count": len(positions),
                "closed_trade_count": len(trades),
                "win_count": wins,
                "loss_count": losses,
                "win_rate": round((wins / total) * 100, 2) if total else DATA_UNAVAILABLE,
                "real_order": False,
                "go_live_allowed": False,
            },
            "open_positions": positions,
            "closed_trades": trades,
            "statement_ledger": ledger,
            "validation_status": "VALIDATED",
            "data_source": "SQLITE_PAPER_ENGINE",
            "timestamp": _now(),
            "real_order": False,
            "go_live_allowed": False,
        }

    @staticmethod
    def _blocked(reason: str, **extra: Any) -> dict[str, Any]:
        return {
            "status": "BLOCKED",
            "reason": reason,
            **extra,
            "real_order": False,
            "go_live_allowed": False,
        }
