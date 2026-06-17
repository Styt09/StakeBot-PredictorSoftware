"""Durable audit logs and evidence reports for ALPHA-GATE X.

Phase 10 stores operational evidence in a local JSONL file. Events are sanitized
before persistence so broker/API secrets are never stored. Corrupt JSONL lines
are returned as AUDIT_LINE_UNREADABLE entries instead of crashing readers.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence
from uuid import uuid4
import json

DEFAULT_AUDIT_PATH = Path(".alpha_gate_state") / "audit_log.jsonl"
SECRET_TOKENS = ("SECRET", "TOKEN", "PASSWORD", "API_KEY", "REQUEST_TOKEN", "ACCESS_TOKEN", "AUTHORIZATION")


class AuditWriteError(RuntimeError):
    """Raised when a required durable audit write fails."""


@dataclass(frozen=True)
class AuditEvent:
    event_type: str
    source: str
    status: str
    symbol: str | None = None
    decision: str | None = None
    blocked_reasons: Sequence[str] = ()
    data_quality: str | None = None
    risk_allowed: bool | None = None
    paper_order_id: str | None = None
    shadow_order_id: str | None = None
    broker_order_id: None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: f"audit-{uuid4()}")
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    go_live_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "source": self.source,
            "symbol": self.symbol,
            "status": self.status,
            "decision": self.decision,
            "blocked_reasons": tuple(str(x) for x in self.blocked_reasons),
            "data_quality": self.data_quality,
            "risk_allowed": self.risk_allowed,
            "paper_order_id": self.paper_order_id,
            "shadow_order_id": self.shadow_order_id,
            "broker_order_id": None,
            "go_live_allowed": False,
            "metadata": sanitize_for_audit(dict(self.metadata or {})),
        }


class DurableAuditLog:
    def __init__(self, path: str | Path = DEFAULT_AUDIT_PATH) -> None:
        self.path = Path(path)

    def write_event(self, event: AuditEvent | Mapping[str, Any]) -> dict[str, Any]:
        payload = event.to_dict() if isinstance(event, AuditEvent) else self._coerce_event(event)
        payload = sanitize_for_audit(payload)
        payload["broker_order_id"] = None
        payload["go_live_allowed"] = False
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
        except OSError as exc:
            raise AuditWriteError(f"AUDIT_WRITE_FAILED:{type(exc).__name__}") from exc
        return payload

    def recent(self, limit: int = 100) -> dict[str, Any]:
        safe_limit = min(max(int(limit or 100), 1), 500)
        events = self.export_events()["events"]
        return {"events": tuple(events[-safe_limit:]), "limit": safe_limit, "total_events": len(events), "audit_storage_path": str(self.path), "go_live_allowed": False}

    def export_events(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"events": (), "total_events": 0, "audit_storage_path": str(self.path), "go_live_allowed": False}
        events: list[dict[str, Any]] = []
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            unreadable = _unreadable_event(0, f"AUDIT_FILE_UNREADABLE:{type(exc).__name__}")
            return {"events": (unreadable,), "total_events": 1, "audit_storage_path": str(self.path), "go_live_allowed": False}
        for idx, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
                if not isinstance(payload, dict):
                    raise ValueError("line is not object")
                events.append(sanitize_for_audit(payload))
            except Exception:
                events.append(_unreadable_event(idx, "AUDIT_LINE_UNREADABLE"))
        return {"events": tuple(events), "total_events": len(events), "audit_storage_path": str(self.path), "go_live_allowed": False}

    def report(self) -> dict[str, Any]:
        events = list(self.export_events()["events"])
        by_event_type: Counter[str] = Counter()
        by_status: Counter[str] = Counter()
        by_symbol: Counter[str] = Counter()
        by_blocked_reason: Counter[str] = Counter()
        for event in events:
            by_event_type[str(event.get("event_type") or "UNKNOWN")] += 1
            by_status[str(event.get("status") or "UNKNOWN")] += 1
            if event.get("symbol"):
                by_symbol[str(event.get("symbol"))] += 1
            for reason in event.get("blocked_reasons") or ():
                by_blocked_reason[str(reason)] += 1
        last_event = events[-1] if events else None
        return {
            "total_events": len(events),
            "last_event": last_event,
            "counts_by_event_type": dict(by_event_type),
            "counts_by_status": dict(by_status),
            "counts_by_symbol": dict(by_symbol),
            "counts_by_blocked_reason": dict(by_blocked_reason),
            "audit_storage_path": str(self.path),
            "go_live_allowed": False,
        }

    def assert_writable(self) -> None:
        self.write_event({"event_type": "AUDIT_WRITE_PROBE", "source": "AUDIT", "status": "PASS"})

    def _coerce_event(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "event_id": str(payload.get("event_id") or f"audit-{uuid4()}"),
            "event_type": str(payload.get("event_type") or "UNKNOWN"),
            "timestamp": str(payload.get("timestamp") or datetime.now(UTC).isoformat()),
            "source": str(payload.get("source") or "UNKNOWN"),
            "symbol": _optional_str(payload.get("symbol")),
            "status": str(payload.get("status") or "UNKNOWN"),
            "decision": _optional_str(payload.get("decision")),
            "blocked_reasons": tuple(str(x) for x in (payload.get("blocked_reasons") or ())),
            "data_quality": _optional_str(payload.get("data_quality")),
            "risk_allowed": payload.get("risk_allowed") if isinstance(payload.get("risk_allowed"), bool) else None,
            "paper_order_id": _optional_str(payload.get("paper_order_id")),
            "shadow_order_id": _optional_str(payload.get("shadow_order_id")),
            "broker_order_id": None,
            "go_live_allowed": False,
            "metadata": sanitize_for_audit(payload.get("metadata") or {}),
        }


def sanitize_for_audit(value: Any) -> Any:
    if isinstance(value, Mapping):
        safe: dict[str, Any] = {}
        for key, item in value.items():
            key_str = str(key)
            if _is_secret_key(key_str):
                safe[key_str] = "***MASKED***" if item not in (None, "") else None
            else:
                safe[key_str] = sanitize_for_audit(item)
        if "go_live_allowed" in safe:
            safe["go_live_allowed"] = False
        if "broker_order_id" in safe:
            safe["broker_order_id"] = None
        return safe
    if isinstance(value, (list, tuple, set)):
        return tuple(sanitize_for_audit(item) for item in value)
    return value


def _is_secret_key(key: str) -> bool:
    upper = key.upper()
    return any(token in upper for token in SECRET_TOKENS)


def _optional_str(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _unreadable_event(line_number: int, reason: str) -> dict[str, Any]:
    return {
        "event_id": f"audit-unreadable-{uuid4()}",
        "event_type": "AUDIT_LINE_UNREADABLE",
        "timestamp": datetime.now(UTC).isoformat(),
        "source": "AUDIT_LOG_READER",
        "symbol": None,
        "status": "ERROR",
        "decision": None,
        "blocked_reasons": (reason,),
        "data_quality": "DATA_UNAVAILABLE",
        "risk_allowed": None,
        "paper_order_id": None,
        "shadow_order_id": None,
        "broker_order_id": None,
        "go_live_allowed": False,
        "metadata": {"line_number": line_number},
    }
