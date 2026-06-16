"""Structured logging and metrics for Phase 9 production hardening."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from time import perf_counter

from .event_bus import RuntimeEvent, RuntimeEventType
from .security import redact_secrets


@dataclass
class RuntimeMetrics:
    runtime_mode: str = "PAPER_TRADING"
    tick_count: int = 0
    candle_count: int = 0
    signal_count: int = 0
    approval_count: int = 0
    preview_count: int = 0
    blocked_real_order_count: int = 0
    reconciliation_pass: int = 0
    reconciliation_fail: int = 0
    stale_feed_incidents: int = 0
    malformed_tick_incidents: int = 0
    persistence_failures: int = 0
    recovery_status: str = "UNKNOWN"
    api_request_count: int = 0
    latency_buckets: dict[str, int] = field(default_factory=lambda: {"lt_50ms": 0, "lt_250ms": 0, "gte_250ms": 0})
    shadow_run_recommendation: str = "UNKNOWN"
    kill_switch_active: bool = False

    def observe_event(self, event: RuntimeEvent) -> None:
        if event.event_type in {RuntimeEventType.TICK_RECEIVED, RuntimeEventType.ZERODHA_TICK_RECEIVED}:
            self.tick_count += 1
        elif event.event_type == RuntimeEventType.CANDLE_FINALIZED:
            self.candle_count += 1
        elif event.event_type == RuntimeEventType.SIGNAL_GENERATED:
            self.signal_count += 1
        elif event.event_type == RuntimeEventType.TRADE_APPROVAL_REQUESTED:
            self.approval_count += 1
        elif event.event_type == RuntimeEventType.ZERODHA_ORDER_PREVIEW_GENERATED:
            self.preview_count += 1
        elif event.event_type == RuntimeEventType.REAL_ORDER_BLOCKED:
            self.blocked_real_order_count += 1
        elif event.event_type == RuntimeEventType.BROKER_RECONCILIATION_PASSED:
            self.reconciliation_pass += 1
        elif event.event_type == RuntimeEventType.BROKER_RECONCILIATION_FAILED:
            self.reconciliation_fail += 1
        elif event.event_type == RuntimeEventType.RUNTIME_PERSISTENCE_FAILED:
            self.persistence_failures += 1
        elif event.event_type == RuntimeEventType.RECOVERY_COMPLETED:
            self.recovery_status = "RECOVERED"
        elif event.event_type == RuntimeEventType.RECOVERY_FAILED:
            self.recovery_status = "SAFE_RECOVERY"
        if event.event_type == RuntimeEventType.RISK_BLOCKED:
            reasons = " ".join(str(reason).lower() for reason in event.payload.get("reasons", ()))
            self.stale_feed_incidents += int("stale" in reasons)
            self.kill_switch_active = self.kill_switch_active or "kill switch" in reasons
        if event.event_type == RuntimeEventType.INSTRUMENT_RESOLUTION_FAILED:
            self.malformed_tick_incidents += 1

    def observe_api_latency(self, elapsed_seconds: float) -> None:
        self.api_request_count += 1
        if elapsed_seconds < 0.05:
            self.latency_buckets["lt_50ms"] += 1
        elif elapsed_seconds < 0.25:
            self.latency_buckets["lt_250ms"] += 1
        else:
            self.latency_buckets["gte_250ms"] += 1


class StructuredLogger:
    def log(self, level: str, message: str, **fields: object) -> str:
        return json.dumps({"level": level, "message": message, **redact_secrets(fields)}, sort_keys=True)


class latency_timer:
    def __init__(self, metrics: RuntimeMetrics) -> None:
        self.metrics = metrics
        self.started = 0.0

    def __enter__(self) -> "latency_timer":
        self.started = perf_counter()
        return self

    def __exit__(self, *exc: object) -> None:
        self.metrics.observe_api_latency(perf_counter() - self.started)
