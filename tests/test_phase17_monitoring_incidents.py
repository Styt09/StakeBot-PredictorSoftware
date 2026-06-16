from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from institutional_trading_platform.alpha_gate_x import TradingMode
from institutional_trading_platform.runtime import (
    AlertRouteType,
    AlertRouter,
    DashboardSummaryService,
    IncidentManager,
    IncidentSeverity,
    IncidentStatus,
    InMemoryAuditStore,
    ManualReviewDecision,
    ManualReviewGate,
    MetricsRegistry,
    RuntimeConfig,
    RuntimeEvent,
    RuntimeEventType,
    SLOTracker,
    ShadowRunGateConfig,
    ShadowRunValidator,
)
from institutional_trading_platform.runtime.api import ReadOnlyRuntimeAPI
from institutional_trading_platform.runtime.evidence_pack import EvidencePackGenerator, REQUIRED_EVIDENCE_SECTIONS
from institutional_trading_platform.validation.robustness import RobustnessRecommendation, RobustnessScorecard

UTC = timezone.utc


def _ready_store() -> InMemoryAuditStore:
    store = InMemoryAuditStore()
    now = datetime(2026, 1, 1, tzinfo=UTC)
    for day in range(30):
        ts = now + timedelta(days=day)
        store.append(RuntimeEvent(RuntimeEventType.ZERODHA_CONNECTED, timestamp=ts))
        store.append(RuntimeEvent(RuntimeEventType.ZERODHA_TICK_RECEIVED, "RELIANCE", timestamp=ts))
        store.append(RuntimeEvent(RuntimeEventType.SIGNAL_GENERATED, payload={"signal": "BUY"}, timestamp=ts))
        store.append(RuntimeEvent(RuntimeEventType.PAPER_PNL_UPDATED, payload={"realized_pnl": float(day + 1), "drawdown_pct": 0.0}, timestamp=ts))
    return store


def _ready_pack(store: InMemoryAuditStore, *, incident_manager: IncidentManager | None = None, slo_status=None, alert_router: AlertRouter | None = None):
    shadow = ShadowRunValidator(store, ShadowRunGateConfig(minimum_sample_count=30, minimum_connection_uptime_pct=90, minimum_profit_factor=0, minimum_win_rate=50))
    metrics = MetricsRegistry()
    metrics.record("runtime_uptime_seconds", 3600)
    metrics.record("execution_quality_score", 95)
    pack = EvidencePackGenerator(store, DashboardSummaryService(store), shadow).generate(config_summary={}, metrics_registry=metrics, incident_manager=incident_manager, slo_status=slo_status, alert_router=alert_router or AlertRouter(audit_store=store))
    pack.sections["robustness_validation_json"] = {"scorecard": RobustnessScorecard(85, 90, 100, 80, 80, 80, 90, 100, 90, RobustnessRecommendation.READY_FOR_MANUAL_REVIEW, (), (), (), False).to_dict()}
    pack.sections["multi_strategy_json"] = {"allocations": {"allocations": {"A": 0.5, "B": 0.5}}, "health_scores": {"A": {"status": "HEALTHY"}, "B": {"status": "HEALTHY"}}, "overlap_warnings": ()}
    pack.sections["options_risk_json"] = {"greeks": {"data_status": "OK"}, "iv_metrics": {"data_status": "OK"}, "expiry_metrics": {"data_status": "OK"}, "concentration_metrics": {"approved": True}, "risk_warnings": (), "go_live_allowed": False}
    pack.sections["execution_realism_json"] = {"execution_reports": ({"fill_ratio": 1.0},), "latency_reports": (), "fill_ratio": 1.0, "warnings": (), "impact_warnings": (), "go_live_allowed": False}

    pack.sections["ha_disaster_recovery_json"] = {"ha_status": {"audit_chain_integrity": True}, "backup_reports": ({"verified": True},), "restore_reports": ({"restore_success": True},), "recovery_readiness": {"recommendation": "READY", "audit_chain_valid": True}, "retention_compliance": {"compliant": True}, "dr_simulations": ({"recovery_success": True},), "business_continuity_report": {"recommendation": "READY_FOR_MANUAL_REVIEW"}, "go_live_allowed": False}

    pack.sections["final_certification_json"] = {"certification_scorecard": {"failed_sections": (), "unavailable_sections": (), "warning_sections": (), "recommendation": "READY_FOR_MANUAL_CERTIFICATION", "go_live_allowed": False}, "readiness_report": {"critical_blockers": (), "recommendation": "READY_FOR_MANUAL_CERTIFICATION", "go_live_allowed": False}, "evidence_quality": {"acceptable": True, "go_live_allowed": False}, "review_workflow": {"completed": True, "go_live_allowed": False}, "review_board_decisions": {"completed": True, "go_live_allowed": False}, "certification_package_metadata": {"package_id": "cert-test", "go_live_allowed": False}, "go_live_allowed": False}
    return pack, shadow


def test_metrics_registry_records_json_and_prometheus() -> None:
    registry = MetricsRegistry()
    registry.record("tick_ingestion_rate", 12.5, labels={"symbol": "RELIANCE"})
    registry.record("ml_research_advisory_status", 1)

    assert registry.latest("tick_ingestion_rate").value == 12.5
    assert registry.snapshot()["go_live_allowed"] is False
    assert "tick_ingestion_rate" in registry.export_json()
    prometheus = registry.export_prometheus()
    assert '# TYPE tick_ingestion_rate gauge' in prometheus
    assert 'tick_ingestion_rate{symbol="RELIANCE"} 12.5' in prometheus


def test_incident_creation_acknowledge_and_resolve() -> None:
    manager = IncidentManager()
    incident = manager.create("stale_feed", IncidentSeverity.CRITICAL, affected_symbols=("RELIANCE",), correlation_id="corr-1")
    assert incident.status == IncidentStatus.OPEN
    assert manager.unresolved_critical() == (incident,)

    acknowledged = manager.acknowledge(incident.incident_id)
    assert acknowledged.status == IncidentStatus.ACKNOWLEDGED
    resolved = manager.resolve(incident.incident_id, now=datetime(2026, 1, 1, tzinfo=UTC))
    assert resolved.status == IncidentStatus.RESOLVED
    assert manager.unresolved_critical() == ()


def test_alert_route_to_audit_log_and_webhook_disabled_by_default() -> None:
    store = InMemoryAuditStore()
    manager = IncidentManager()
    incident = manager.create("zerodha_auth_failure", IncidentSeverity.WARNING, affected_symbols=("NIFTY",))
    router = AlertRouter(audit_store=store)
    results = router.route(incident)

    assert any(result.route_type == AlertRouteType.AUDIT_STORE and result.delivered for result in results)
    assert any(result.route_type == AlertRouteType.WEBHOOK_PLACEHOLDER and not result.delivered for result in results)
    assert store.all_events()[0].event_type == RuntimeEventType.ALERT_EMITTED
    assert router.configured_for_manual_review is True


def test_unresolved_critical_incident_blocks_manual_review() -> None:
    store = _ready_store()
    manager = IncidentManager()
    manager.create("persistence_failure", IncidentSeverity.CRITICAL)
    pack, shadow = _ready_pack(store, incident_manager=manager, alert_router=AlertRouter(audit_store=store))

    result = ManualReviewGate(min_samples=30, min_profit_factor=0, min_win_rate=50).evaluate(shadow.status(), pack, runbook_followed=True)
    assert result.decision == ManualReviewDecision.CONTINUE_SHADOW
    assert "no_unresolved_critical_incidents" in result.failure_reasons
    assert result.go_live_allowed is False


def test_slo_failure_blocks_manual_review() -> None:
    store = _ready_store()
    slo = SLOTracker().evaluate(uptime_pct=80, feed_freshness_seconds=10, persistence_available_pct=99, reconciliation_freshness_seconds=10, api_latency_ms=100, recovery_time_seconds=100)
    pack, shadow = _ready_pack(store, slo_status=slo, alert_router=AlertRouter(audit_store=store))

    result = ManualReviewGate(min_samples=30, min_profit_factor=0, min_win_rate=50).evaluate(shadow.status(), pack, runbook_followed=True)
    assert result.decision == ManualReviewDecision.CONTINUE_SHADOW
    assert "slo_targets_acceptable" in result.failure_reasons


def test_monitoring_json_evidence_included_and_ready_when_clean() -> None:
    store = _ready_store()
    pack, shadow = _ready_pack(store, alert_router=AlertRouter(audit_store=store))
    result = ManualReviewGate(min_samples=30, min_profit_factor=0, min_win_rate=50).evaluate(shadow.status(), pack, runbook_followed=True)

    assert "monitoring_json" in REQUIRED_EVIDENCE_SECTIONS
    assert pack.sections["monitoring_json"]["monitoring_readiness"] is True
    assert pack.sections["monitoring_json"]["go_live_allowed"] is False
    assert result.decision == ManualReviewDecision.READY_FOR_MANUAL_REVIEW


def test_read_only_monitoring_api_facades() -> None:
    store = InMemoryAuditStore()
    registry = MetricsRegistry()
    registry.record("api_request_latency_ms", 25)
    api = ReadOnlyRuntimeAPI(
        store,
        DashboardSummaryService(store),
        ShadowRunValidator(store),
        strategy_context={
            "monitoring_metrics": registry.snapshot(),
            "monitoring_metrics_prometheus": registry.export_prometheus(),
            "monitoring_incidents": (),
            "monitoring_incidents_open": (),
            "monitoring_slo": {"targets_acceptable": True, "go_live_allowed": False},
            "monitoring_alerts": (),
        },
    )

    assert api.monitoring_metrics()["go_live_allowed"] is False
    assert "api_request_latency_ms" in api.monitoring_metrics_prometheus()
    assert api.monitoring_incidents() == ()
    assert not hasattr(api, "place_order")


def test_live_auto_rejected_and_no_real_order_path() -> None:
    assert not hasattr(MetricsRegistry(), "place_order")
    assert not hasattr(IncidentManager(), "place_order")
    with pytest.raises(ValueError, match="rejects LIVE_AUTO"):
        RuntimeConfig(trading_mode=TradingMode.LIVE_AUTO)
