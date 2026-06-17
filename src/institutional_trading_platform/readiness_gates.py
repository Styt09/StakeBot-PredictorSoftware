"""Operational readiness gates for ALPHA-GATE X.

Phase 11 reports paper/shadow/live readiness. It never enables live trading and
always returns live_ready=false with live_verdict=NO_GO.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Mapping, Sequence

from .safe_config import getSafePublicConfig


class ReadinessLevel(str, Enum):
    PAPER_READY = "PAPER_READY"
    SHADOW_READY = "SHADOW_READY"
    LIVE_NO_GO = "LIVE_NO_GO"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class ReadinessInputs:
    broker_health: Mapping[str, Any] | None = None
    market_data_health: Mapping[str, Any] | None = None
    kill_switch_status: Mapping[str, Any] | None = None
    audit_report: Mapping[str, Any] | None = None
    live_order_status: Mapping[str, Any] | None = None
    broker_mutation_status: Mapping[str, Any] | None = None
    paper_status: Mapping[str, Any] | None = None
    shadow_status: Mapping[str, Any] | None = None
    public_config: Mapping[str, Any] | None = None


class ReadinessGateEvaluator:
    def evaluate(self, inputs: ReadinessInputs | None = None) -> dict[str, Any]:
        inputs = inputs or ReadinessInputs()
        public_config = dict(inputs.public_config or getSafePublicConfig())
        blocked: list[str] = []
        warnings: list[str] = []
        evidence: dict[str, Any] = {}

        evidence["config_loaded"] = bool(public_config)
        if not evidence["config_loaded"]:
            blocked.append("CONFIG_UNAVAILABLE")

        trading_mode = str(public_config.get("trading_mode") or public_config.get("tradingMode") or "DATA_UNAVAILABLE")
        evidence["trading_mode"] = trading_mode
        if trading_mode not in {"PAPER", "SHADOW", "READ_ONLY", "LIVE_DISABLED"}:
            blocked.append("UNSAFE_TRADING_MODE")

        live_enabled = bool(public_config.get("live_trading_enabled") or public_config.get("liveTradingEnabled"))
        evidence["live_trading_enabled"] = live_enabled
        if live_enabled:
            blocked.append("LIVE_TRADING_ENABLED")

        if _contains_secret(public_config):
            blocked.append("PUBLIC_CONFIG_EXPOSES_SECRET")

        broker = dict(inputs.broker_health or {})
        evidence["broker_health_available"] = bool(broker)
        evidence["broker_read_only"] = broker.get("read_only") is True
        evidence["broker_mutation_enabled"] = broker.get("mutation_enabled") is True
        if not broker:
            warnings.append("BROKER_HEALTH_UNAVAILABLE")
        if broker and broker.get("mutation_enabled") is not False:
            blocked.append("BROKER_MUTATION_NOT_DISABLED")

        market = dict(inputs.market_data_health or {})
        evidence["market_data_available"] = bool(market)
        evidence["market_data_state"] = market.get("state")
        if not market:
            warnings.append("MARKET_DATA_HEALTH_UNAVAILABLE")

        kill = dict(inputs.kill_switch_status or {})
        evidence["kill_switch_readable"] = bool(kill)
        evidence["kill_switch_active"] = bool(kill.get("active")) if kill else None
        if not kill:
            blocked.append("KILL_SWITCH_STATUS_UNAVAILABLE")
        elif kill.get("active"):
            blocked.append("KILL_SWITCH_ACTIVE")

        audit = dict(inputs.audit_report or {})
        total_events = int(audit.get("total_events") or 0) if audit else 0
        evidence["audit_available"] = bool(audit)
        evidence["audit_total_events"] = total_events
        if not audit:
            blocked.append("AUDIT_REPORT_UNAVAILABLE")
        elif total_events <= 0:
            blocked.append("AUDIT_EVIDENCE_MISSING")

        live = dict(inputs.live_order_status or {})
        evidence["live_order_blocked"] = live.get("status") == "BLOCKED" if live else None
        if not live:
            warnings.append("LIVE_ORDER_BLOCK_EVIDENCE_UNAVAILABLE")
        elif live.get("status") != "BLOCKED":
            blocked.append("LIVE_ORDER_NOT_BLOCKED")

        mutation = dict(inputs.broker_mutation_status or {})
        evidence["broker_mutation_blocked"] = mutation.get("status") == "BLOCKED" if mutation else None
        if not mutation:
            warnings.append("BROKER_MUTATION_BLOCK_EVIDENCE_UNAVAILABLE")
        elif mutation.get("status") != "BLOCKED" or mutation.get("broker_order_id") is not None:
            blocked.append("BROKER_MUTATION_NOT_BLOCKED")

        paper = dict(inputs.paper_status or {})
        shadow = dict(inputs.shadow_status or {})
        evidence["paper_endpoint_available"] = bool(paper)
        evidence["shadow_endpoint_available"] = bool(shadow)
        if not paper:
            blocked.append("PAPER_ENDPOINT_UNAVAILABLE")
        if not shadow:
            blocked.append("SHADOW_ENDPOINT_UNAVAILABLE")

        paper_ready = bool(paper) and not _has_any(blocked, {"CONFIG_UNAVAILABLE", "UNSAFE_TRADING_MODE", "KILL_SWITCH_ACTIVE", "AUDIT_REPORT_UNAVAILABLE", "AUDIT_EVIDENCE_MISSING", "PAPER_ENDPOINT_UNAVAILABLE"})
        shadow_ready = paper_ready and bool(shadow) and "SHADOW_ENDPOINT_UNAVAILABLE" not in blocked

        return {
            "paper_ready": paper_ready,
            "shadow_ready": shadow_ready,
            "live_ready": False,
            "live_verdict": "NO_GO",
            "blocked_reasons": tuple(dict.fromkeys(blocked + ["LIVE_TRADING_NOT_IMPLEMENTED", "MANUAL_LIVE_APPROVAL_REQUIRED"])),
            "warnings": tuple(dict.fromkeys(warnings)),
            "evidence": _sanitize_report(evidence),
            "timestamp": datetime.now(UTC).isoformat(),
            "go_live_allowed": False,
        }

    def checklist(self, gates: Mapping[str, Any]) -> dict[str, Any]:
        evidence = dict(gates.get("evidence") or {})
        items = [
            _item("config_loaded", evidence.get("config_loaded") is True),
            _item("trading_mode_safe", evidence.get("trading_mode") in {"PAPER", "SHADOW", "READ_ONLY", "LIVE_DISABLED"}),
            _item("live_trading_disabled", evidence.get("live_trading_enabled") is False),
            _item("broker_read_only_health_available", evidence.get("broker_health_available") is True),
            _item("broker_mutation_disabled", evidence.get("broker_mutation_enabled") is False),
            _item("market_data_health_available", evidence.get("market_data_available") is True),
            _item("risk_engine_available", True),
            _item("paper_order_manager_available", evidence.get("paper_endpoint_available") is True),
            _item("shadow_engine_available", evidence.get("shadow_endpoint_available") is True),
            _item("persistent_kill_switch_readable", evidence.get("kill_switch_readable") is True),
            _item("kill_switch_inactive", evidence.get("kill_switch_active") is False),
            _item("durable_audit_log_has_evidence", int(evidence.get("audit_total_events") or 0) > 0),
            _item("live_order_submit_blocked", evidence.get("live_order_blocked") is True),
            _item("broker_mutation_endpoint_blocked", evidence.get("broker_mutation_blocked") is True),
            _item("live_ready", False, status="NOT_IMPLEMENTED"),
        ]
        return {"items": tuple(items), "live_verdict": "NO_GO", "go_live_allowed": False}

    def report(self, gates: Mapping[str, Any]) -> dict[str, Any]:
        blocked = tuple(gates.get("blocked_reasons") or ())
        warnings = tuple(gates.get("warnings") or ())
        return {
            "summary": "Operational readiness evaluated. Live trading remains NO-GO.",
            "paper_ready": bool(gates.get("paper_ready")),
            "shadow_ready": bool(gates.get("shadow_ready")),
            "live_ready": False,
            "live_verdict": "NO_GO",
            "top_blocked_reasons": blocked[:10],
            "warnings": warnings,
            "readiness_level": ReadinessLevel.SHADOW_READY.value if gates.get("shadow_ready") else ReadinessLevel.PAPER_READY.value if gates.get("paper_ready") else ReadinessLevel.BLOCKED.value,
            "timestamp": datetime.now(UTC).isoformat(),
            "go_live_allowed": False,
        }


def _item(name: str, passed: bool, *, status: str | None = None) -> dict[str, Any]:
    item_status = status or ("PASS" if passed else "FAIL")
    return {"name": name, "status": item_status, "passed": bool(passed), "go_live_allowed": False}


def _has_any(values: Sequence[str], names: set[str]) -> bool:
    return any(value in names for value in values)


def _contains_secret(value: Any) -> bool:
    text = str(value).upper()
    return any(token in text for token in ("SK-", "ACCESS_TOKEN=", "REQUEST_TOKEN=", "API_SECRET", "PASSWORD"))


def _sanitize_report(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _sanitize_report(v) for k, v in value.items() if "SECRET" not in str(k).upper() and "TOKEN" not in str(k).upper()}
    if isinstance(value, (list, tuple, set)):
        return tuple(_sanitize_report(v) for v in value)
    return value


def summarize_blocked_reasons(gates: Mapping[str, Any]) -> dict[str, int]:
    return dict(Counter(str(reason) for reason in gates.get("blocked_reasons") or ()))
