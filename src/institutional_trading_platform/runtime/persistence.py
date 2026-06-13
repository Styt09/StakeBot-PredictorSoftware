"""Durable SQLite audit store, snapshots, and idempotency for Phase 8."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Protocol

from .event_bus import EventBus, RuntimeEvent, RuntimeEventType
from .security import redact_secrets


class PersistenceUnavailable(RuntimeError):
    """Raised when durable audit persistence is unavailable."""


class DuplicateIdempotencyKey(RuntimeError):
    """Raised when a persisted idempotency key is reused."""


@dataclass(frozen=True)
class RuntimeStateSnapshot:
    """Recoverable runtime state snapshot persisted as JSON."""

    snapshot_id: str
    current_mode: str
    subscribed_symbols: tuple[str, ...] = ()
    open_paper_positions: tuple[dict[str, object], ...] = ()
    closed_paper_positions: tuple[dict[str, object], ...] = ()
    approved_trade_plans: tuple[dict[str, object], ...] = ()
    pending_approvals: tuple[dict[str, object], ...] = ()
    cash: float = 0.0
    equity: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    kill_switch_active: bool = False
    reconciliation_status: str = "UNKNOWN"
    last_processed_candle_timestamp: datetime | None = None
    last_tick_timestamp_by_symbol: dict[str, datetime] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class AuditRepository(Protocol):
    """Persistence interface for SQLite now and PostgreSQL later."""

    def append(self, event: RuntimeEvent) -> None: ...
    def save_snapshot(self, snapshot: RuntimeStateSnapshot) -> None: ...
    def register_idempotency_key(self, key: str) -> None: ...
    def health(self) -> dict[str, object]: ...


class SQLiteAuditStore:
    """SQLite-backed audit store with PostgreSQL-friendly interface boundaries."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self.initialize()

    def initialize(self) -> None:
        """Create schema safely; repeated calls are non-destructive."""

        with self._conn:
            self._conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)")
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runtime_events (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    correlation_id TEXT,
                    symbol TEXT,
                    source TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_runtime_events_correlation ON runtime_events(correlation_id)")
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_runtime_events_symbol ON runtime_events(symbol)")
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_runtime_events_type ON runtime_events(event_type)")
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_runtime_events_severity ON runtime_events(severity)")
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_runtime_events_timestamp ON runtime_events(timestamp)")
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runtime_snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            self._conn.execute("CREATE TABLE IF NOT EXISTS processed_idempotency_keys (key TEXT PRIMARY KEY, created_at TEXT NOT NULL)")
            self._conn.execute("INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES(1, ?)", (_dt(datetime.now(timezone.utc)),))


    def transaction(self):
        """Return a SQLite transaction boundary for event/snapshot/approval/preview/idempotency operations."""

        return self._conn

    def append(self, event: RuntimeEvent) -> None:
        payload_json = _payload_json(event.payload)
        source = getattr(event, "source", "runtime")
        severity = getattr(event, "severity", "INFO")
        try:
            with self._conn:
                self._conn.execute(
                    """
                    INSERT INTO runtime_events(event_id, event_type, timestamp, correlation_id, symbol, source, severity, payload_json, created_at)
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (event.event_id, event.event_type.value, _dt(event.timestamp), event.correlation_id, event.symbol, source, severity, payload_json, _dt(datetime.now(timezone.utc))),
                )
        except sqlite3.Error as exc:
            raise PersistenceUnavailable(str(exc)) from exc

    def all_events(self) -> tuple[RuntimeEvent, ...]:
        return self.latest_events(limit=1_000_000)

    def by_event_id(self, event_id: str) -> RuntimeEvent | None:
        rows = self._query("SELECT * FROM runtime_events WHERE event_id = ?", (event_id,))
        return self._event(rows[0]) if rows else None

    def by_correlation_id(self, correlation_id: str) -> tuple[RuntimeEvent, ...]:
        return tuple(self._event(row) for row in self._query("SELECT * FROM runtime_events WHERE correlation_id = ? ORDER BY timestamp, created_at", (correlation_id,)))

    def by_symbol(self, symbol: str) -> tuple[RuntimeEvent, ...]:
        return tuple(self._event(row) for row in self._query("SELECT * FROM runtime_events WHERE symbol = ? ORDER BY timestamp, created_at", (symbol,)))

    def by_event_type(self, event_type: RuntimeEventType) -> tuple[RuntimeEvent, ...]:
        return tuple(self._event(row) for row in self._query("SELECT * FROM runtime_events WHERE event_type = ? ORDER BY timestamp, created_at", (event_type.value,)))

    def by_severity(self, severity: str) -> tuple[RuntimeEvent, ...]:
        return tuple(self._event(row) for row in self._query("SELECT * FROM runtime_events WHERE severity = ? ORDER BY timestamp, created_at", (severity,)))

    def by_time_range(self, start: datetime, end: datetime) -> tuple[RuntimeEvent, ...]:
        return tuple(self._event(row) for row in self._query("SELECT * FROM runtime_events WHERE timestamp >= ? AND timestamp <= ? ORDER BY timestamp, created_at", (_dt(start), _dt(end))))

    def latest_events(self, limit: int = 100) -> tuple[RuntimeEvent, ...]:
        rows = self._query("SELECT * FROM runtime_events ORDER BY timestamp DESC, created_at DESC LIMIT ?", (limit,))
        return tuple(self._event(row) for row in reversed(rows))

    def export_json(self) -> str:
        return json.dumps([_event_json(event) for event in self.all_events()], indent=2, sort_keys=True)

    def save_snapshot(self, snapshot: RuntimeStateSnapshot) -> None:
        try:
            with self._conn:
                self._conn.execute(
                    "INSERT OR REPLACE INTO runtime_snapshots(snapshot_id, created_at, mode, payload_json) VALUES(?, ?, ?, ?)",
                    (snapshot.snapshot_id, _dt(snapshot.created_at), snapshot.current_mode, _payload_json(asdict(snapshot))),
                )
        except sqlite3.Error as exc:
            raise PersistenceUnavailable(str(exc)) from exc

    def latest_snapshot(self) -> RuntimeStateSnapshot | None:
        rows = self._query("SELECT payload_json FROM runtime_snapshots ORDER BY created_at DESC LIMIT 1", ())
        if not rows:
            return None
        return _snapshot(json.loads(rows[0]["payload_json"]))

    def register_idempotency_key(self, key: str) -> None:
        try:
            with self._conn:
                self._conn.execute("INSERT INTO processed_idempotency_keys(key, created_at) VALUES(?, ?)", (key, _dt(datetime.now(timezone.utc))))
        except sqlite3.IntegrityError as exc:
            raise DuplicateIdempotencyKey(key) from exc
        except sqlite3.Error as exc:
            raise PersistenceUnavailable(str(exc)) from exc

    def has_idempotency_key(self, key: str) -> bool:
        return bool(self._query("SELECT key FROM processed_idempotency_keys WHERE key = ?", (key,)))

    def health(self) -> dict[str, object]:
        try:
            self._conn.execute("SELECT 1")
            return {"status": "ok", "backend": "sqlite", "path": self.path}
        except sqlite3.Error as exc:
            return {"status": "failed", "backend": "sqlite", "error": str(exc)}

    def _query(self, sql: str, params: Iterable[object]) -> list[sqlite3.Row]:
        try:
            return list(self._conn.execute(sql, tuple(params)))
        except sqlite3.Error as exc:
            raise PersistenceUnavailable(str(exc)) from exc

    @staticmethod
    def _event(row: sqlite3.Row) -> RuntimeEvent:
        return RuntimeEvent(
            event_type=RuntimeEventType(row["event_type"]),
            symbol=row["symbol"],
            payload=json.loads(row["payload_json"]),
            correlation_id=row["correlation_id"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            event_id=row["event_id"],
            source=row["source"],
            severity=row["severity"],
        )


class PersistentEventBus(EventBus):
    """Event bus that durably writes every event before publishing success."""

    def __init__(self, audit_store: SQLiteAuditStore) -> None:
        super().__init__()
        self.audit_store = audit_store

    def publish(self, event: RuntimeEvent) -> RuntimeEvent:
        try:
            self.audit_store.append(event)
        except PersistenceUnavailable:
            # If possible, try to persist a failure marker; otherwise re-raise so
            # callers block trading/approval decisions.
            try:
                failure = RuntimeEvent(RuntimeEventType.RUNTIME_PERSISTENCE_FAILED, event.symbol, {"failed_event_id": event.event_id}, event.correlation_id, source="persistence", severity="CRITICAL")
                self.audit_store.append(failure)
            finally:
                raise
        self.events.append(event)
        for handler in self._subscribers:
            handler(event)
        return event


def _payload_json(payload: object) -> str:
    try:
        return json.dumps(redact_secrets(_jsonable(payload)), sort_keys=True)
    except TypeError as exc:
        raise ValueError("payload must be JSON serializable") from exc


def _jsonable(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "value"):
        return getattr(value, "value")
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value


def _event_json(event: RuntimeEvent) -> dict[str, object]:
    return {
        "event_id": event.event_id,
        "event_type": event.event_type.value,
        "timestamp": event.timestamp.isoformat(),
        "correlation_id": event.correlation_id,
        "symbol": event.symbol,
        "source": event.source,
        "severity": event.severity,
        "payload": _jsonable(event.payload),
    }


def _snapshot(data: dict[str, object]) -> RuntimeStateSnapshot:
    last_candle = data.get("last_processed_candle_timestamp")
    last_ticks = data.get("last_tick_timestamp_by_symbol") or {}
    return RuntimeStateSnapshot(
        snapshot_id=str(data["snapshot_id"]),
        current_mode=str(data["current_mode"]),
        subscribed_symbols=tuple(data.get("subscribed_symbols", ())),
        open_paper_positions=tuple(data.get("open_paper_positions", ())),
        closed_paper_positions=tuple(data.get("closed_paper_positions", ())),
        approved_trade_plans=tuple(data.get("approved_trade_plans", ())),
        pending_approvals=tuple(data.get("pending_approvals", ())),
        cash=float(data.get("cash", 0.0)),
        equity=float(data.get("equity", 0.0)),
        realized_pnl=float(data.get("realized_pnl", 0.0)),
        unrealized_pnl=float(data.get("unrealized_pnl", 0.0)),
        kill_switch_active=bool(data.get("kill_switch_active", False)),
        reconciliation_status=str(data.get("reconciliation_status", "UNKNOWN")),
        last_processed_candle_timestamp=datetime.fromisoformat(last_candle) if isinstance(last_candle, str) else None,
        last_tick_timestamp_by_symbol={str(key): datetime.fromisoformat(value) for key, value in dict(last_ticks).items()},
        created_at=datetime.fromisoformat(str(data["created_at"])),
    )


def _dt(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return value.isoformat()
