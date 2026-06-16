from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from institutional_trading_platform.alpha_gate_x import TradingMode
from institutional_trading_platform.runtime import (
    AlertManager,
    AlertType,
    DashboardSummaryService,
    EventBus,
    InMemoryAuditStore,
    ReadOnlyRuntimeAPI,
    RuntimeConfig,
    RuntimeEvent,
    RuntimeEventType,
    ShadowRunGateConfig,
    ShadowRunRecommendation,
    ShadowRunValidator,
)

UTC = timezone.utc


def _store_with_bus() -> tuple[InMemoryAuditStore, EventBus]:
    store = InMemoryAuditStore()
    bus = EventBus()
    bus.subscribe(store.append)
    return store, bus


def test_dashboard_status_works_with_empty_audit_store() -> None:
    store = InMemoryAuditStore()
    summary = DashboardSummaryService(store).summary(now=datetime(2026, 1, 1, tzinfo=UTC))

    assert summary.runtime_mode == TradingMode.PAPER_TRADING
    assert summary.zerodha_auth_status == "UNKNOWN"
    assert summary.go_live_allowed is False


def test_dashboard_reflects_zerodha_connected_disconnected_and_stale_feed() -> None:
    store, bus = _store_with_bus()
    now = datetime(2026, 1, 1, 9, 15, tzinfo=UTC)
    bus.publish(RuntimeEvent(RuntimeEventType.ZERODHA_CONNECTED, timestamp=now))
    bus.publish(RuntimeEvent(RuntimeEventType.ZERODHA_TICK_RECEIVED, "RELIANCE", timestamp=now))
    connected = DashboardSummaryService(store, subscribed_symbols=("RELIANCE",)).summary(now=now + timedelta(seconds=1))
    bus.publish(RuntimeEvent(RuntimeEventType.ZERODHA_DISCONNECTED, timestamp=now + timedelta(seconds=2)))
    stale = DashboardSummaryService(store, subscribed_symbols=("RELIANCE",)).summary(now=now + timedelta(seconds=10), stale_after_seconds=5)

    assert connected.zerodha_auth_status == "CONNECTED"
    assert connected.websocket_status == "CONNECTED"
    assert stale.stale_feed is True


def test_alerts_emitted_for_auth_failure_and_reconciliation_failure() -> None:
    store, bus = _store_with_bus()
    alerts = AlertManager(bus, store)

    auth_alert = alerts.handle_event(RuntimeEvent(RuntimeEventType.ZERODHA_AUTH_FAILED, payload={"reasons": ("missing",)}))
    recon_alert = alerts.handle_event(RuntimeEvent(RuntimeEventType.BROKER_RECONCILIATION_FAILED, payload={"reasons": ("unexpected open position RELIANCE",)}))

    assert auth_alert is not None and auth_alert.alert_type == AlertType.AUTH_FAILED
    assert recon_alert is not None and recon_alert.alert_type == AlertType.UNEXPECTED_BROKER_POSITION
    assert len(store.by_event_type(RuntimeEventType.ALERT_EMITTED)) == 2


def test_pending_approval_and_exit_suggestion_appear_on_dashboard_and_api() -> None:
    store, bus = _store_with_bus()
    bus.publish(RuntimeEvent(RuntimeEventType.TRADE_APPROVAL_REQUESTED, "RELIANCE", {"request_id": "r1"}, "corr-1"))
    bus.publish(RuntimeEvent(RuntimeEventType.ZERODHA_ORDER_PREVIEW_GENERATED, "RELIANCE", {}, "corr-1"))
    bus.publish(RuntimeEvent(RuntimeEventType.EXIT_SUGGESTED, "RELIANCE", {"reason": "TARGET"}, "corr-1"))
    dashboard = DashboardSummaryService(store, subscribed_symbols=("RELIANCE",))
    api = ReadOnlyRuntimeAPI(store, dashboard, ShadowRunValidator(store))

    summary = dashboard.summary()

    assert summary.approval_requests == 1
    assert summary.order_previews == 1
    assert summary.exit_suggestions == 1
    assert len(api.approvals_pending()) == 1
    assert api.health()["read_only"] is True


def test_shadow_run_does_not_pass_before_30_trading_days() -> None:
    store, bus = _store_with_bus()
    bus.publish(RuntimeEvent(RuntimeEventType.SIGNAL_GENERATED, payload={"signal": "BUY"}, timestamp=datetime(2026, 1, 1, tzinfo=UTC)))
    status = ShadowRunValidator(store, ShadowRunGateConfig(minimum_sample_count=1, minimum_connection_uptime_pct=0, minimum_profit_factor=0, minimum_win_rate=0)).status()

    assert status.recommendation == ShadowRunRecommendation.CONTINUE_SHADOW
    assert status.go_live_allowed is False
    assert any("trading days" in reason for reason in status.failure_reasons)


def test_shadow_run_fails_with_reconciliation_drift_and_safety_violation() -> None:
    store, bus = _store_with_bus()
    now = datetime(2026, 1, 1, tzinfo=UTC)
    for day in range(30):
        bus.publish(RuntimeEvent(RuntimeEventType.SIGNAL_GENERATED, payload={"signal": "BUY"}, timestamp=now + timedelta(days=day)))
    bus.publish(RuntimeEvent(RuntimeEventType.BROKER_RECONCILIATION_FAILED, payload={"reasons": ("quantity mismatch",)}, timestamp=now))
    bus.publish(RuntimeEvent(RuntimeEventType.REAL_ORDER_BLOCKED, timestamp=now))

    status = ShadowRunValidator(store, ShadowRunGateConfig(minimum_sample_count=1, minimum_connection_uptime_pct=0, minimum_profit_factor=0, minimum_win_rate=0)).status()

    assert status.recommendation == ShadowRunRecommendation.CONTINUE_SHADOW
    assert any("reconciliation drift" in reason for reason in status.failure_reasons)
    assert any("safety violation" in reason for reason in status.failure_reasons)


def test_shadow_run_can_return_ready_for_manual_review_only() -> None:
    store, bus = _store_with_bus()
    now = datetime(2026, 1, 1, tzinfo=UTC)
    for day in range(30):
        bus.publish(RuntimeEvent(RuntimeEventType.ZERODHA_CONNECTED, timestamp=now + timedelta(days=day)))
        bus.publish(RuntimeEvent(RuntimeEventType.ZERODHA_TICK_RECEIVED, "RELIANCE", timestamp=now + timedelta(days=day)))
        bus.publish(RuntimeEvent(RuntimeEventType.SIGNAL_GENERATED, payload={"signal": "BUY"}, timestamp=now + timedelta(days=day)))
        bus.publish(RuntimeEvent(RuntimeEventType.PAPER_PNL_UPDATED, payload={"realized_pnl": float(day + 1), "drawdown_pct": 0.0}, timestamp=now + timedelta(days=day)))

    status = ShadowRunValidator(store, ShadowRunGateConfig(minimum_sample_count=30, minimum_connection_uptime_pct=90, minimum_profit_factor=0, minimum_win_rate=50)).status()

    assert status.recommendation == ShadowRunRecommendation.READY_FOR_MANUAL_REVIEW
    assert status.go_live_allowed is False
    assert status.recommendation.value != "LIVE_AUTO_READY"


def test_read_only_api_endpoints_do_not_place_orders_and_live_auto_rejected() -> None:
    store = InMemoryAuditStore()
    api = ReadOnlyRuntimeAPI(store, DashboardSummaryService(store), ShadowRunValidator(store))

    assert api.runtime_events() == ()
    assert api.runtime_events_by_correlation("missing") == ()
    assert api.runtime_symbols("RELIANCE") == ()
    assert api.runtime_report() == {"available": False, "go_live_allowed": False}
    assert api.reconciliation_status() == "UNKNOWN"
    assert api.risk_status()["go_live_allowed"] is False
    assert api.shadow_run_status()["go_live_allowed"] is False
    assert not hasattr(api, "place_order")
    with pytest.raises(ValueError, match="rejects LIVE_AUTO"):
        RuntimeConfig(trading_mode=TradingMode.LIVE_AUTO)
