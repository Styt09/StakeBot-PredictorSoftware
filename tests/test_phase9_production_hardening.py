from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from institutional_trading_platform.alpha_gate_x import AlphaSignal, TradingMode
from institutional_trading_platform.broker import ZerodhaOrderSafetyWrapper
from institutional_trading_platform.runtime import (
    ConfigProfile,
    CrashRecoveryService,
    DashboardSummaryService,
    EventBus,
    HealthCheckService,
    InMemoryAuditStore,
    ProductionRuntimeConfig,
    ReadOnlyRuntimeAPI,
    RecoveryMode,
    RuntimeConfig,
    RuntimeEvent,
    RuntimeEventType,
    RuntimeMetrics,
    SQLiteAuditStore,
    ShadowRunValidator,
    StructuredLogger,
)
from institutional_trading_platform.runtime.persistence import PersistenceUnavailable
from institutional_trading_platform.runtime.security import redact_secrets, safe_error_response

UTC = timezone.utc


def test_invalid_config_and_missing_env_fail_closed(tmp_path) -> None:
    config = ProductionRuntimeConfig.from_env({"ALPHA_GATE_PROFILE": "BAD", "AUDIT_DB_PATH": str(tmp_path / "audit.db")})
    approval = ProductionRuntimeConfig.from_env({"ALPHA_GATE_PROFILE": "APPROVAL_REQUIRED", "AUDIT_DB_PATH": str(tmp_path / "audit.db")})

    assert config.profile == ConfigProfile.SAFE_RECOVERY
    assert not config.valid
    assert approval.trading_mode == TradingMode.APPROVAL_REQUIRED
    assert not approval.valid
    with pytest.raises(ValueError):
        approval.assert_valid()


def test_live_auto_rejected_by_config_and_runtime(tmp_path) -> None:
    config = ProductionRuntimeConfig.from_env({"TRADING_MODE": "LIVE_AUTO", "AUDIT_DB_PATH": str(tmp_path / "audit.db")})

    assert not config.valid
    assert config.trading_mode == TradingMode.PAPER_TRADING
    with pytest.raises(ValueError, match="rejects LIVE_AUTO"):
        RuntimeConfig(trading_mode=TradingMode.LIVE_AUTO)


def test_readiness_fails_when_persistence_down_safe_recovery_stale_feed_or_reconciliation_drift(tmp_path) -> None:
    store = SQLiteAuditStore(tmp_path / "audit.db")
    memory = InMemoryAuditStore()
    now = datetime(2026, 1, 1, tzinfo=UTC)
    memory.append(RuntimeEvent(RuntimeEventType.TICK_RECEIVED, "RELIANCE", timestamp=now - timedelta(seconds=30)))
    memory.append(RuntimeEvent(RuntimeEventType.BROKER_RECONCILIATION_FAILED, payload={"reasons": ("drift",)}, timestamp=now))
    dashboard = DashboardSummaryService(memory)
    recovery = CrashRecoveryService(store)
    recovery.last_status = recovery.last_status.__class__(RecoveryMode.SAFE_RECOVERY, None, 0, 0, ("unsafe",))
    health = HealthCheckService(ProductionRuntimeConfig.from_env({"AUDIT_DB_PATH": str(tmp_path / "audit.db")}), store, dashboard, ShadowRunValidator(store), recovery)

    readiness = health.readiness(now=now, in_market_session=True)

    assert not readiness.ok
    assert any(check.name == "recovery" and not check.ok for check in readiness.checks)
    assert any(check.name == "reconciliation" and not check.ok for check in readiness.checks)
    assert any(check.name == "market_feed" and not check.ok for check in readiness.checks)

    class DownStore(SQLiteAuditStore):
        def health(self):  # type: ignore[override]
            return {"status": "failed", "error": "down"}

    down = DownStore(tmp_path / "down.db")
    assert not HealthCheckService(ProductionRuntimeConfig.from_env({"AUDIT_DB_PATH": str(tmp_path / "audit.db")}), down, DashboardSummaryService(InMemoryAuditStore()), ShadowRunValidator(down)).readiness().ok


def test_secret_redaction_logs_events_and_safe_errors(tmp_path) -> None:
    redacted = redact_secrets({"ZERODHA_API_KEY": "abc", "nested": {"access_token": "secret"}})
    log = StructuredLogger().log("INFO", "startup", ZERODHA_ACCESS_TOKEN="secret", normal="ok")
    store = SQLiteAuditStore(tmp_path / "audit.db")
    event = RuntimeEvent(RuntimeEventType.ZERODHA_CONNECTED, payload={"api_key": "abc", "normal": "ok"})
    store.append(event)

    assert redacted["ZERODHA_API_KEY"] == "<REDACTED>"
    assert "secret" not in log
    assert store.by_event_id(event.event_id).payload["api_key"] == "<REDACTED>"
    assert "secret" not in safe_error_response(ValueError("access_token=secret"))["message"]


def test_unsafe_broker_action_emits_blocked_event_and_no_real_order(tmp_path) -> None:
    bus = EventBus()
    preview = ZerodhaOrderSafetyWrapper(event_bus=bus).preview(correlation_id="unsafe", symbol="RELIANCE", exchange="NSE", side=AlphaSignal.BUY, quantity=1)
    result = ZerodhaOrderSafetyWrapper(event_bus=bus).submit_real_order(preview)

    assert result.status.value == "NO_REAL_ORDER_PLACED"
    assert any(event.event_type == RuntimeEventType.REAL_ORDER_BLOCKED for event in bus.events)
    assert any(event.event_type == RuntimeEventType.UNSAFE_ACTION_BLOCKED for event in bus.events)


def test_transaction_failure_blocks_preview(tmp_path) -> None:
    class FailingStore(SQLiteAuditStore):
        def register_idempotency_key(self, key):  # type: ignore[override]
            raise PersistenceUnavailable("transaction failed")

    with pytest.raises(PersistenceUnavailable):
        ZerodhaOrderSafetyWrapper(idempotency_store=FailingStore(tmp_path / "audit.db")).preview(correlation_id="tx", symbol="RELIANCE", exchange="NSE", side=AlphaSignal.BUY, quantity=1)


def test_metrics_observe_events_and_latency() -> None:
    metrics = RuntimeMetrics(runtime_mode="SHADOW")
    for event_type in (RuntimeEventType.TICK_RECEIVED, RuntimeEventType.CANDLE_FINALIZED, RuntimeEventType.SIGNAL_GENERATED, RuntimeEventType.TRADE_APPROVAL_REQUESTED, RuntimeEventType.ZERODHA_ORDER_PREVIEW_GENERATED, RuntimeEventType.REAL_ORDER_BLOCKED, RuntimeEventType.BROKER_RECONCILIATION_PASSED, RuntimeEventType.BROKER_RECONCILIATION_FAILED, RuntimeEventType.RUNTIME_PERSISTENCE_FAILED):
        metrics.observe_event(RuntimeEvent(event_type))
    metrics.observe_event(RuntimeEvent(RuntimeEventType.RISK_BLOCKED, payload={"reasons": ("stale data", "kill switch active")}))
    metrics.observe_api_latency(0.01)

    assert metrics.tick_count == 1
    assert metrics.preview_count == 1
    assert metrics.persistence_failures == 1
    assert metrics.stale_feed_incidents == 1
    assert metrics.kill_switch_active is True
    assert metrics.api_request_count == 1


def test_deployment_files_exist_and_api_no_order_path() -> None:
    for file_name in ("Dockerfile", "docker-compose.yml", "Makefile", "scripts/init_db.py", "scripts/export_audit_json.py", "OPERATIONAL_RUNBOOK.md"):
        assert Path(file_name).exists()
    api = ReadOnlyRuntimeAPI(InMemoryAuditStore(), DashboardSummaryService(InMemoryAuditStore()), ShadowRunValidator(InMemoryAuditStore()))
    assert not hasattr(api, "place_order")
    assert api.health()["go_live_allowed"] is False
