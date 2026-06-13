from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from institutional_trading_platform.alpha_gate_x import AlphaSignal, TradingMode
from institutional_trading_platform.alpha_gate_x_indicators import ConfidenceGrade, IndicatorSignalOutput, TradingProfile
from institutional_trading_platform.broker import ApprovalModeService, BrokerReconciliationService, BrokerStateSnapshot, LocalApprovalState, ZerodhaOrderSafetyWrapper
from institutional_trading_platform.runtime import (
    CrashRecoveryService,
    DashboardSummaryService,
    DuplicateIdempotencyKey,
    PersistentEventBus,
    ReadOnlyRuntimeAPI,
    RecoveryMode,
    RuntimeConfig,
    RuntimeEvent,
    RuntimeEventType,
    RuntimeStateSnapshot,
    SQLiteAuditStore,
    ShadowRunGateConfig,
    ShadowRunRecommendation,
    ShadowRunValidator,
)
from institutional_trading_platform.runtime.persistence import PersistenceUnavailable

UTC = timezone.utc


def _signal(correlation_id: str = "corr-1") -> IndicatorSignalOutput:
    return IndicatorSignalOutput(
        symbol="RELIANCE",
        timeframe="5m",
        trading_profile=TradingProfile.INTRADAY,
        signal=AlphaSignal.BUY,
        final_score=0.8,
        confidence=0.9,
        confidence_grade=ConfidenceGrade.A,
        entry_reference=100.0,
        stop_loss=99.0,
        target_1=102.0,
        target_2=103.0,
        expected_move=1.0,
        risk_status=__import__("institutional_trading_platform.alpha_gate_x", fromlist=["RiskStatus"]).RiskStatus.PASS,
        component_scores={},
        unavailable_components=(),
        reasons=("test",),
        correlation_id=correlation_id,
    )


def test_sqlite_audit_store_initializes_safely_and_event_queries_work(tmp_path) -> None:
    db = tmp_path / "audit.db"
    store = SQLiteAuditStore(db)
    store.initialize()
    event = RuntimeEvent(RuntimeEventType.SIGNAL_GENERATED, "RELIANCE", {"signal": "BUY"}, "corr-1", timestamp=datetime(2026, 1, 1, tzinfo=UTC), severity="INFO")
    store.append(event)

    assert store.by_event_id(event.event_id) == event
    assert store.by_correlation_id("corr-1") == (event,)
    assert store.by_symbol("RELIANCE") == (event,)
    assert store.by_event_type(RuntimeEventType.SIGNAL_GENERATED) == (event,)
    assert store.by_severity("INFO") == (event,)
    assert store.by_time_range(datetime(2025, 12, 31, tzinfo=UTC), datetime(2026, 1, 2, tzinfo=UTC)) == (event,)
    assert store.latest_events(1) == (event,)
    assert store.health()["status"] == "ok"


def test_persistence_failure_blocks_approval_request() -> None:
    class FailingStore(SQLiteAuditStore):
        def append(self, event):  # type: ignore[override]
            raise PersistenceUnavailable("disk full")

    store = FailingStore(":memory:")
    bus = PersistentEventBus(store)
    recon = BrokerReconciliationService(event_bus=bus)

    with pytest.raises(PersistenceUnavailable):
        recon.reconcile(BrokerStateSnapshot(updated_at=datetime(2026, 1, 1, tzinfo=UTC)), LocalApprovalState(), now=datetime(2026, 1, 1, tzinfo=UTC))


def test_approval_request_cannot_exist_without_audit_event(tmp_path) -> None:
    store = SQLiteAuditStore(tmp_path / "audit.db")
    bus = PersistentEventBus(store)
    recon = BrokerReconciliationService(event_bus=bus)
    recon.reconcile(BrokerStateSnapshot(updated_at=datetime(2026, 1, 1, tzinfo=UTC)), LocalApprovalState(), now=datetime(2026, 1, 1, tzinfo=UTC))
    service = ApprovalModeService(RuntimeConfig(trading_mode=TradingMode.APPROVAL_REQUIRED), recon, ZerodhaOrderSafetyWrapper(event_bus=bus), event_bus=bus)

    request = service.request_approval(_signal("audit-corr"))

    assert request.correlation_id == "audit-corr"
    assert store.by_correlation_id("audit-corr")[0].event_type == RuntimeEventType.TRADE_APPROVAL_REQUESTED


def test_snapshot_save_restore_and_api_status(tmp_path) -> None:
    store = SQLiteAuditStore(tmp_path / "audit.db")
    snapshot = RuntimeStateSnapshot(
        snapshot_id="snap-1",
        current_mode="PAPER_TRADING",
        subscribed_symbols=("RELIANCE",),
        cash=1000,
        equity=1010,
        realized_pnl=10,
        last_processed_candle_timestamp=datetime(2026, 1, 1, 9, 20, tzinfo=UTC),
        last_tick_timestamp_by_symbol={"RELIANCE": datetime(2026, 1, 1, 9, 21, tzinfo=UTC)},
    )
    store.save_snapshot(snapshot)

    restored = store.latest_snapshot()
    api = ReadOnlyRuntimeAPI(store, DashboardSummaryService(store), ShadowRunValidator(store))

    assert restored == snapshot
    assert api.snapshot_status()["mode"] == "PAPER_TRADING"
    assert api.persistence_health()["status"] == "ok"


def test_recovery_emits_started_and_completed(tmp_path) -> None:
    store = SQLiteAuditStore(tmp_path / "audit.db")
    bus = PersistentEventBus(store)
    store.save_snapshot(RuntimeStateSnapshot("snap-1", "PAPER_TRADING"))
    recovery = CrashRecoveryService(store, event_bus=bus)

    status = recovery.recover(reconciliation_passed=True)

    assert status.mode == RecoveryMode.RECOVERED
    assert store.by_event_type(RuntimeEventType.RECOVERY_STARTED)
    assert store.by_event_type(RuntimeEventType.RECOVERY_COMPLETED)


def test_recovery_failure_enters_safe_recovery(tmp_path) -> None:
    store = SQLiteAuditStore(tmp_path / "audit.db")
    bus = PersistentEventBus(store)
    recovery = CrashRecoveryService(store, event_bus=bus)

    status = recovery.recover(reconciliation_passed=False)

    assert status.mode == RecoveryMode.SAFE_RECOVERY
    assert status.trading_blocked
    assert store.by_event_type(RuntimeEventType.RECOVERY_FAILED)


def test_duplicate_preview_blocked_after_restart(tmp_path) -> None:
    db = tmp_path / "audit.db"
    store = SQLiteAuditStore(db)
    wrapper = ZerodhaOrderSafetyWrapper(idempotency_store=store)
    wrapper.preview(correlation_id="dup", symbol="RELIANCE", exchange="NSE", side=AlphaSignal.BUY, quantity=1)
    restarted = SQLiteAuditStore(db)
    wrapper_after_restart = ZerodhaOrderSafetyWrapper(idempotency_store=restarted)

    with pytest.raises(DuplicateIdempotencyKey):
        wrapper_after_restart.preview(correlation_id="dup", symbol="RELIANCE", exchange="NSE", side=AlphaSignal.BUY, quantity=1)


def test_shadow_run_status_survives_restart_and_api_reads_persisted_events(tmp_path) -> None:
    db = tmp_path / "audit.db"
    store = SQLiteAuditStore(db)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    for day in range(30):
        store.append(RuntimeEvent(RuntimeEventType.ZERODHA_CONNECTED, timestamp=now + timedelta(days=day)))
        store.append(RuntimeEvent(RuntimeEventType.ZERODHA_TICK_RECEIVED, "RELIANCE", timestamp=now + timedelta(days=day)))
        store.append(RuntimeEvent(RuntimeEventType.SIGNAL_GENERATED, payload={"signal": "BUY"}, timestamp=now + timedelta(days=day)))
        store.append(RuntimeEvent(RuntimeEventType.PAPER_PNL_UPDATED, payload={"realized_pnl": float(day + 1), "drawdown_pct": 0.0}, timestamp=now + timedelta(days=day)))
    restarted = SQLiteAuditStore(db)
    shadow = ShadowRunValidator(restarted, ShadowRunGateConfig(minimum_sample_count=30, minimum_connection_uptime_pct=90, minimum_profit_factor=0, minimum_win_rate=50))
    api = ReadOnlyRuntimeAPI(restarted, DashboardSummaryService(restarted), shadow)

    status = shadow.status()

    assert status.recommendation == ShadowRunRecommendation.READY_FOR_MANUAL_REVIEW
    assert status.go_live_allowed is False
    assert len(api.latest_persisted_events(5)) == 5
    assert api.event_lookup(restarted.latest_events(1)[0].event_id) is not None
    assert api.shadow_run_status()["go_live_allowed"] is False


def test_live_auto_still_rejected_and_no_real_orders(tmp_path) -> None:
    with pytest.raises(ValueError, match="rejects LIVE_AUTO"):
        RuntimeConfig(trading_mode=TradingMode.LIVE_AUTO)
    store = SQLiteAuditStore(tmp_path / "audit.db")
    preview = ZerodhaOrderSafetyWrapper(idempotency_store=store).preview(correlation_id="safe", symbol="RELIANCE", exchange="NSE", side=AlphaSignal.BUY, quantity=1)
    result = ZerodhaOrderSafetyWrapper().submit_real_order(preview)
    assert store.by_correlation_id("safe")[0].event_type == RuntimeEventType.ZERODHA_ORDER_PREVIEW_GENERATED
    assert result.status.value == "NO_REAL_ORDER_PLACED"
