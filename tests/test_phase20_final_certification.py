from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from institutional_trading_platform.alpha_gate_x import TradingMode
from institutional_trading_platform.runtime import (
    BackupManager,
    BackupRetentionManager,
    BackupType,
    BusinessContinuityReporter,
    CertificationRecommendation,
    CertificationStatus,
    DashboardSummaryService,
    DisasterRecoverySimulator,
    DisasterScenario,
    EvidenceQualityValidator,
    FinalCertificationFramework,
    FinalOperationalChecklist,
    FinalReadinessReporter,
    FourEyesControl,
    GovernanceAction,
    GovernanceEvent,
    GovernanceRole,
    GovernanceSeverity,
    HAHealthStatus,
    InMemoryAuditStore,
    ManualCertificationPackageGenerator,
    ManualReviewDecision,
    ManualReviewGate,
    RecoveryReadinessValidator,
    RestoreManager,
    ReviewBoard,
    ReviewBoardRole,
    ReviewStageStatus,
    RuntimeConfig,
    RuntimeEvent,
    RuntimeEventType,
    ShadowRunGateConfig,
    ShadowRunValidator,
    TamperEvidentAuditChain,
    TradingDeskWorkflow,
)
from institutional_trading_platform.runtime.api import ReadOnlyRuntimeAPI
from institutional_trading_platform.runtime.evidence_pack import EvidencePackGenerator, REQUIRED_EVIDENCE_SECTIONS
from institutional_trading_platform.validation.robustness import RobustnessRecommendation, RobustnessScorecard

UTC = timezone.utc


def _store() -> InMemoryAuditStore:
    store = InMemoryAuditStore()
    start = datetime(2026, 1, 1, tzinfo=UTC)
    for day in range(30):
        ts = start + timedelta(days=day)
        store.append(RuntimeEvent(RuntimeEventType.ZERODHA_CONNECTED, timestamp=ts))
        store.append(RuntimeEvent(RuntimeEventType.ZERODHA_TICK_RECEIVED, "RELIANCE", timestamp=ts))
        store.append(RuntimeEvent(RuntimeEventType.SIGNAL_GENERATED, payload={"signal": "BUY"}, timestamp=ts))
        store.append(RuntimeEvent(RuntimeEventType.PAPER_PNL_UPDATED, payload={"realized_pnl": float(day + 1), "drawdown_pct": 0.0}, timestamp=ts))
    return store


def _chain() -> TamperEvidentAuditChain:
    chain = TamperEvidentAuditChain()
    chain.append(GovernanceEvent.create(actor="ops", actor_role=GovernanceRole.OPERATOR, action=GovernanceAction.EVIDENCE_PACK_EXPORTED, affected_resource="certification", reason="final certification", severity=GovernanceSeverity.INFO, timestamp=datetime(2026, 1, 1, tzinfo=UTC)))
    return chain


def _workflow() -> TradingDeskWorkflow:
    workflow = TradingDeskWorkflow()
    workflow.analyst_review("analyst", True, "market data reviewed")
    workflow.risk_review("risk", True, "risk reviewed")
    workflow.operations_review("ops", True, "ops reviewed")
    workflow.compliance_review("compliance", True, "compliance reviewed")
    workflow.final_signoff("final", True, "manual certification only")
    return workflow


def _base_pack(tmp_path):
    store = _store()
    shadow = ShadowRunValidator(store, ShadowRunGateConfig(minimum_sample_count=30, minimum_connection_uptime_pct=90, minimum_profit_factor=0, minimum_win_rate=50))
    source = tmp_path / "audit.db"
    source.write_text("audit", encoding="utf-8")
    backup_manager = BackupManager(tmp_path / "backups")
    metadata = backup_manager.create_backup(source, BackupType.FULL)
    verification = backup_manager.verify_backup(metadata)
    restore = RestoreManager().restore(metadata, tmp_path / "restore.db", backup_manager)
    dr = DisasterRecoverySimulator().simulate(DisasterScenario.RESTART_RECOVERY)
    chain = _chain()
    readiness = RecoveryReadinessValidator().validate(backup_metadata=metadata, verification_report=verification, restore_report=restore, recovery_reports=(dr,), audit_chain=chain)
    retention = BackupRetentionManager().evaluate((metadata,))
    bc = BusinessContinuityReporter().build(backup_report=verification, restore_report=restore, readiness_report=readiness, retention_report=retention, dr_reports=(dr,))
    approval = FourEyesControl().request_approval(resource="manual_review", requested_by="alice", approved_by="bob", action=GovernanceAction.MANUAL_REVIEW_COMPLETED)
    pack = EvidencePackGenerator(store, DashboardSummaryService(store), shadow).generate(config_summary={"profile": "LOCAL"}, governance_audit_chain=chain, four_eyes_approvals=(approval,), ha_status=HAHealthStatus.evaluate(database_availability=True, backup_availability=True, restore_readiness=True, recovery_readiness=True, audit_chain_integrity=True, reconciliation_readiness=True, shadow_run_continuity=True), backup_reports=(verification,), restore_reports=(restore,), recovery_readiness_report=readiness, retention_compliance_report=retention, dr_simulation_reports=(dr,), business_continuity_report=bc)
    pack.sections["validation_report_json"] = {"go_live_allowed": False, "recommendation": "CONTINUE_SHADOW"}
    pack.sections["runtime_snapshot_json"] = {"mode": "PAPER_TRADING", "go_live_allowed": False}
    pack.sections["research_ml_json"] = {"recommendation": "CONTINUE_RESEARCH", "go_live_allowed": False}
    pack.sections["robustness_validation_json"] = {"scorecard": RobustnessScorecard(85, 90, 100, 80, 80, 80, 90, 100, 90, RobustnessRecommendation.READY_FOR_MANUAL_REVIEW, (), (), (), False).to_dict()}
    pack.sections["multi_strategy_json"] = {"allocations": {"allocations": {"A": 0.5, "B": 0.5}}, "health_scores": {"A": {"status": "HEALTHY"}, "B": {"status": "HEALTHY"}}, "overlap_warnings": ()}
    pack.sections["options_risk_json"] = {"greeks": {"data_status": "OK"}, "iv_metrics": {"data_status": "OK"}, "expiry_metrics": {"data_status": "OK"}, "concentration_metrics": {"approved": True}, "risk_warnings": (), "go_live_allowed": False}
    pack.sections["execution_realism_json"] = {"execution_reports": ({"fill_ratio": 1.0},), "latency_reports": (), "fill_ratio": 1.0, "warnings": (), "impact_warnings": (), "go_live_allowed": False}
    return pack, shadow


def _certify(pack):
    framework = FinalCertificationFramework()
    reports = framework.certify(pack.sections)
    scorecard = framework.scorecard(reports)
    required = tuple(section for section in REQUIRED_EVIDENCE_SECTIONS if section != "final_certification_json")
    quality = EvidenceQualityValidator().validate(pack.sections, required)
    readiness = FinalReadinessReporter().build(scorecard, quality)
    workflow = _workflow()
    package = ManualCertificationPackageGenerator().generate(scorecard, readiness, evidence_summary={"complete": quality.acceptable}, compliance_summary={}, governance_summary={}, risk_summary={})
    return framework, reports, scorecard, quality, readiness, workflow, package


def test_certification_pass_warning_fail_and_scorecard(tmp_path) -> None:
    pack, _ = _base_pack(tmp_path)
    framework, reports, scorecard, _, _, _, _ = _certify(pack)
    assert all(report.status in {CertificationStatus.PASS, CertificationStatus.PASS_WITH_WARNINGS} for report in reports)
    assert scorecard.recommendation == CertificationRecommendation.READY_FOR_MANUAL_CERTIFICATION
    assert scorecard.go_live_allowed is False

    warning = framework.certify_area(next(area for area in framework.AREA_EVIDENCE if area.value == "Options Risk"), {**pack.sections, "options_risk_json": {"warnings": ("minor warning",), "go_live_allowed": False}})
    assert warning.status == CertificationStatus.PASS_WITH_WARNINGS
    failed = framework.certify_area(next(area for area in framework.AREA_EVIDENCE if area.value == "HA/DR"), {**pack.sections, "ha_disaster_recovery_json": {"go_live_allowed": True}})
    assert failed.status == CertificationStatus.FAIL


def test_evidence_quality_and_operational_checklist(tmp_path) -> None:
    pack, _ = _base_pack(tmp_path)
    _, _, scorecard, quality, _, _, _ = _certify(pack)
    assert quality.acceptable is True
    missing = EvidenceQualityValidator().validate({}, ("shadow_run_status_json", "monitoring_json"))
    assert missing.acceptable is False
    assert missing.missing_shadow_data is True
    checklist = FinalOperationalChecklist.build(shadow_run_complete=True, reconciliation_clean=True, no_critical_incidents=True, governance_pass=True, compliance_pass=True, audit_chain_valid=True, backup_verified=True, restore_tested=True, robustness_pass=True, execution_realism_pass=True, monitoring_pass=True, evidence_complete=quality.acceptable)
    assert checklist.recommendation == "READY_FOR_MANUAL_CERTIFICATION"
    assert scorecard.go_live_allowed is False


def test_review_workflow_rejection_and_review_board_decisions() -> None:
    workflow = TradingDeskWorkflow()
    workflow.analyst_review("analyst", True)
    rejection = workflow.risk_review("risk", False, "drawdown concern")
    assert rejection.status == ReviewStageStatus.REJECTED
    assert rejection.rejection_reason
    assert workflow.board.completed is False

    board = ReviewBoard()
    decision = board.record_decision(ReviewBoardRole.COMPLIANCE_REVIEWER, ReviewStageStatus.APPROVED, reviewer="comp", notes="ok")
    assert decision.reviewer == "comp"
    assert board.to_dict()["go_live_allowed"] is False


def test_readiness_package_evidence_pack_and_manual_review_gate(tmp_path) -> None:
    pack, shadow = _base_pack(tmp_path)
    _, _, scorecard, quality, readiness, workflow, package = _certify(pack)
    # Reuse existing pack sections while replacing only final certification evidence for manual gate coverage.
    pack.sections["final_certification_json"] = __import__("institutional_trading_platform.runtime.certification", fromlist=["final_certification_evidence_section"]).final_certification_evidence_section(scorecard=scorecard, readiness_report=readiness, evidence_quality=quality, workflow=workflow, certification_package=package)
    result = ManualReviewGate(min_samples=30, min_profit_factor=0, min_win_rate=50).evaluate(shadow.status(), pack, runbook_followed=True)

    assert "final_certification_json" in REQUIRED_EVIDENCE_SECTIONS
    assert package.metadata["go_live_allowed"] is False
    assert "READY_FOR_MANUAL_CERTIFICATION" in package.to_markdown()
    assert pack.sections["final_certification_json"]["go_live_allowed"] is False
    assert result.decision == ManualReviewDecision.READY_FOR_MANUAL_REVIEW
    assert result.go_live_allowed is False
    missing_pack = EvidencePackGenerator(_store(), DashboardSummaryService(_store()), shadow).generate(config_summary={})
    assert missing_pack.sections["final_certification_json"]["data_status"] == "DATA_UNAVAILABLE"


def test_read_only_certification_api_live_auto_rejected_and_no_order_path() -> None:
    store = InMemoryAuditStore()
    api = ReadOnlyRuntimeAPI(store, DashboardSummaryService(store), ShadowRunValidator(store), strategy_context={"certification_status": {"recommendation": "READY_FOR_MANUAL_CERTIFICATION", "go_live_allowed": False}})
    assert api.certification_status()["go_live_allowed"] is False
    assert api.certification_package()["go_live_allowed"] is False
    assert not hasattr(api, "place_order")
    with pytest.raises(ValueError, match="rejects LIVE_AUTO"):
        RuntimeConfig(trading_mode=TradingMode.LIVE_AUTO)
