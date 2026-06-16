from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from institutional_trading_platform.alpha_gate_x import TradingMode
from institutional_trading_platform.runtime import (
    AlertRouter,
    GovernanceApprovalStatus,
    ComplianceEngine,
    ComplianceRecommendation,
    DashboardSummaryService,
    FourEyesControl,
    GovernanceAction,
    GovernanceEvent,
    GovernancePermission,
    GovernanceRole,
    GovernanceSeverity,
    InMemoryAuditStore,
    ManualReviewDecision,
    ManualReviewGate,
    MetricsRegistry,
    PolicyEngine,
    PolicyName,
    RoleBasedAccessControl,
    RuntimeConfig,
    RuntimeEvent,
    RuntimeEventType,
    ShadowRunGateConfig,
    ShadowRunValidator,
    TamperEvidentAuditChain,
)
from institutional_trading_platform.runtime.evidence_pack import EvidencePackGenerator, REQUIRED_EVIDENCE_SECTIONS
from institutional_trading_platform.validation.robustness import RobustnessRecommendation, RobustnessScorecard

UTC = timezone.utc


def _event(actor: str = "alice", action: GovernanceAction = GovernanceAction.CONFIG_CHANGE_REQUESTED) -> GovernanceEvent:
    return GovernanceEvent.create(
        actor=actor,
        actor_role=GovernanceRole.OPERATOR,
        action=action,
        affected_resource="risk.max_daily_loss",
        reason="shadow validation control change",
        previous_value=1.0,
        new_value=0.8,
        approval_status=GovernanceApprovalStatus.PENDING,
        severity=GovernanceSeverity.INFO,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
    )


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


def _ready_pack(store: InMemoryAuditStore, **governance_kwargs):
    shadow = ShadowRunValidator(store, ShadowRunGateConfig(minimum_sample_count=30, minimum_connection_uptime_pct=90, minimum_profit_factor=0, minimum_win_rate=50))
    metrics = MetricsRegistry()
    metrics.record("runtime_uptime_seconds", 3600)
    pack = EvidencePackGenerator(store, DashboardSummaryService(store), shadow).generate(config_summary={}, metrics_registry=metrics, alert_router=AlertRouter(audit_store=store), **governance_kwargs)
    pack.sections["robustness_validation_json"] = {"scorecard": RobustnessScorecard(85, 90, 100, 80, 80, 80, 90, 100, 90, RobustnessRecommendation.READY_FOR_MANUAL_REVIEW, (), (), (), False).to_dict()}
    pack.sections["multi_strategy_json"] = {"allocations": {"allocations": {"A": 0.5, "B": 0.5}}, "health_scores": {"A": {"status": "HEALTHY"}, "B": {"status": "HEALTHY"}}, "overlap_warnings": ()}
    pack.sections["options_risk_json"] = {"greeks": {"data_status": "OK"}, "iv_metrics": {"data_status": "OK"}, "expiry_metrics": {"data_status": "OK"}, "concentration_metrics": {"approved": True}, "risk_warnings": (), "go_live_allowed": False}
    pack.sections["execution_realism_json"] = {"execution_reports": ({"fill_ratio": 1.0},), "latency_reports": (), "fill_ratio": 1.0, "warnings": (), "impact_warnings": (), "go_live_allowed": False}

    pack.sections["ha_disaster_recovery_json"] = {"ha_status": {"audit_chain_integrity": True}, "backup_reports": ({"verified": True},), "restore_reports": ({"restore_success": True},), "recovery_readiness": {"recommendation": "READY", "audit_chain_valid": True}, "retention_compliance": {"compliant": True}, "dr_simulations": ({"recovery_success": True},), "business_continuity_report": {"recommendation": "READY_FOR_MANUAL_REVIEW"}, "go_live_allowed": False}

    pack.sections["final_certification_json"] = {"certification_scorecard": {"failed_sections": (), "unavailable_sections": (), "warning_sections": (), "recommendation": "READY_FOR_MANUAL_CERTIFICATION", "go_live_allowed": False}, "readiness_report": {"critical_blockers": (), "recommendation": "READY_FOR_MANUAL_CERTIFICATION", "go_live_allowed": False}, "evidence_quality": {"acceptable": True, "go_live_allowed": False}, "review_workflow": {"completed": True, "go_live_allowed": False}, "review_board_decisions": {"completed": True, "go_live_allowed": False}, "certification_package_metadata": {"package_id": "cert-test", "go_live_allowed": False}, "go_live_allowed": False}
    return pack, shadow


def test_governance_event_creation() -> None:
    event = _event()
    payload = event.canonical_payload()
    assert event.governance_event_id.startswith("gov-")
    assert payload["actor"] == "alice"
    assert payload["actor_role"] == "OPERATOR"
    assert payload["action"] == "config_change_requested"


def test_audit_hash_chain_verification_modified_and_missing_detection() -> None:
    chain = TamperEvidentAuditChain()
    first = chain.append(_event("alice"))
    chain.append(_event("bob", GovernanceAction.CONFIG_CHANGE_APPROVED))
    assert chain.verify_full_chain().chain_valid is True
    assert first.previous_hash == TamperEvidentAuditChain.GENESIS_HASH

    chain._events[1] = replace(chain._events[1], event=_event("mallory"))
    assert chain.verify_full_chain().chain_valid is False
    assert any("event hash mismatch" in failure for failure in chain.detect_missing_or_modified_event())

    missing = TamperEvidentAuditChain()
    missing.append(_event("alice"))
    missing.append(_event("bob"))
    missing.append(_event("carol"))
    del missing._events[1]
    assert missing.verify_full_chain().chain_valid is False
    assert any("chain index mismatch" in failure or "previous hash mismatch" in failure for failure in missing.detect_missing_or_modified_event())


def test_role_permission_checks_and_no_role_can_enable_live_auto() -> None:
    rbac = RoleBasedAccessControl()
    assert rbac.has_permission(GovernanceRole.VIEWER, GovernancePermission.VIEW_REPORTS)
    assert not rbac.has_permission(GovernanceRole.VIEWER, GovernancePermission.CHANGE_RISK_LIMIT)
    for role in GovernanceRole:
        assert rbac.can_enable_live_auto(role) is False
    assert rbac.summary()["live_auto_permission"] is False


def test_four_eyes_same_actor_blocked() -> None:
    control = FourEyesControl()
    blocked = control.request_approval(resource="risk.max_daily_loss", requested_by="alice", approved_by="alice", action=GovernanceAction.RISK_LIMIT_CHANGED)
    allowed = control.request_approval(resource="risk.max_daily_loss", requested_by="alice", approved_by="bob", action=GovernanceAction.RISK_LIMIT_CHANGED)
    assert blocked.approved is False
    assert "same actor" in blocked.reason
    assert allowed.approved is True


def test_policy_violation_generated_and_live_auto_always_blocks() -> None:
    violations = PolicyEngine().evaluate({"trading_mode": "LIVE_AUTO", "real_order_enabled": True, "go_live_allowed": True})
    policies = {violation.policy for violation in violations}
    assert PolicyName.LIVE_AUTO_FORBIDDEN in policies
    assert PolicyName.REAL_ORDER_FORBIDDEN_BY_DEFAULT in policies
    assert PolicyName.GO_LIVE_FALSE_REQUIRED in policies
    event = violations[0].to_event()
    assert event.action == GovernanceAction.GOVERNANCE_POLICY_VIOLATION
    assert event.approval_status == GovernanceApprovalStatus.BLOCKED


def test_compliance_report_blocks_when_evidence_missing_and_passes_with_required_evidence() -> None:
    engine = ComplianceEngine()
    blocked = engine.build_report(audit_chain_verified=True, evidence_pack_exported=False, risk_limits_reviewed=False, manual_review_completed=False, incidents_resolved=True, monitoring_slo_met=True, reconciliation_clean=True, strategy_robustness_present=True, execution_realism_present=True, options_risk_present_if_fno_enabled=True, no_unsafe_broker_action=True, no_live_auto=True)
    ready = engine.build_report(audit_chain_verified=True, evidence_pack_exported=True, risk_limits_reviewed=True, manual_review_completed=True, incidents_resolved=True, monitoring_slo_met=True, reconciliation_clean=True, strategy_robustness_present=True, execution_realism_present=True, options_risk_present_if_fno_enabled=True, no_unsafe_broker_action=True, no_live_auto=True)
    assert blocked.recommendation in {ComplianceRecommendation.CONTINUE_SHADOW, ComplianceRecommendation.BLOCKED_FOR_COMPLIANCE_REVIEW}
    assert "evidence_pack_exported" in blocked.failure_reasons
    assert ready.recommendation == ComplianceRecommendation.READY_FOR_MANUAL_REVIEW
    assert ready.go_live_allowed is False


def test_governance_compliance_evidence_and_manual_review_gate() -> None:
    store = _ready_store()
    chain = TamperEvidentAuditChain()
    chain.append(_event("alice", GovernanceAction.MANUAL_REVIEW_STARTED))
    approval = FourEyesControl().request_approval(resource="manual_review", requested_by="alice", approved_by="bob", action=GovernanceAction.MANUAL_REVIEW_COMPLETED)
    report = ComplianceEngine().build_report(audit_chain_verified=True, evidence_pack_exported=True, risk_limits_reviewed=True, manual_review_completed=True, incidents_resolved=True, monitoring_slo_met=True, reconciliation_clean=True, strategy_robustness_present=True, execution_realism_present=True, options_risk_present_if_fno_enabled=True, no_unsafe_broker_action=True, no_live_auto=True)
    pack, shadow = _ready_pack(store, governance_audit_chain=chain, compliance_report=report, four_eyes_approvals=(approval,))

    result = ManualReviewGate(min_samples=30, min_profit_factor=0, min_win_rate=50).evaluate(shadow.status(), pack, runbook_followed=True)
    assert "governance_compliance_json" in REQUIRED_EVIDENCE_SECTIONS
    assert pack.sections["governance_compliance_json"]["audit_chain_verification"]["chain_valid"] is True
    assert pack.sections["governance_compliance_json"]["compliance_checklist"]["passed"] is True
    assert result.decision == ManualReviewDecision.READY_FOR_MANUAL_REVIEW
    assert result.go_live_allowed is False


def test_manual_review_requires_compliance_pass_and_blocks_policy_violation() -> None:
    store = _ready_store()
    violation = PolicyEngine().evaluate({"trading_mode": "LIVE_AUTO", "go_live_allowed": False})[0]
    report = ComplianceEngine().build_report(audit_chain_verified=True, evidence_pack_exported=True, risk_limits_reviewed=True, manual_review_completed=True, incidents_resolved=True, monitoring_slo_met=True, reconciliation_clean=True, strategy_robustness_present=True, execution_realism_present=True, options_risk_present_if_fno_enabled=True, no_unsafe_broker_action=True, no_live_auto=True)
    pack, shadow = _ready_pack(store, policy_violations=(violation,), compliance_report=report)

    result = ManualReviewGate(min_samples=30, min_profit_factor=0, min_win_rate=50).evaluate(shadow.status(), pack, runbook_followed=True)
    assert result.decision == ManualReviewDecision.CONTINUE_SHADOW
    assert "no_unresolved_critical_policy_violation" in result.failure_reasons


def test_read_only_governance_api_and_no_order_path() -> None:
    rbac = RoleBasedAccessControl()
    store = InMemoryAuditStore()
    from institutional_trading_platform.runtime.api import ReadOnlyRuntimeAPI

    api = ReadOnlyRuntimeAPI(store, DashboardSummaryService(store), ShadowRunValidator(store), strategy_context={"governance_permissions": rbac.summary(), "governance_events": ()})
    assert api.governance_permissions()["live_auto_permission"] is False
    assert api.governance_events() == ()
    assert not hasattr(api, "place_order")


def test_live_auto_rejected_and_no_real_order_path() -> None:
    assert not hasattr(TamperEvidentAuditChain(), "place_order")
    assert not hasattr(PolicyEngine(), "place_order")
    with pytest.raises(ValueError, match="rejects LIVE_AUTO"):
        RuntimeConfig(trading_mode=TradingMode.LIVE_AUTO)
