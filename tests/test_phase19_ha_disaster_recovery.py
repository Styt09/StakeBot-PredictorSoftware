from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from institutional_trading_platform.alpha_gate_x import TradingMode
from institutional_trading_platform.runtime import (
    BackupManager,
    BackupRetentionManager,
    BackupType,
    BusinessContinuityRecommendation,
    BusinessContinuityReporter,
    DashboardSummaryService,
    DisasterRecoverySimulator,
    DisasterScenario,
    FourEyesControl,
    GovernanceAction,
    GovernanceEvent,
    GovernanceRole,
    GovernanceSeverity,
    HAHealthStatus,
    HAState,
    InMemoryAuditStore,
    ManualReviewDecision,
    ManualReviewGate,
    RecoveryReadinessRecommendation,
    RecoveryReadinessValidator,
    RestoreManager,
    RuntimeConfig,
    RuntimeEvent,
    RuntimeEventType,
    ShadowRunGateConfig,
    ShadowRunValidator,
    TamperEvidentAuditChain,
)
from institutional_trading_platform.runtime.api import ReadOnlyRuntimeAPI
from institutional_trading_platform.runtime.evidence_pack import EvidencePackGenerator, REQUIRED_EVIDENCE_SECTIONS
from institutional_trading_platform.validation.robustness import RobustnessRecommendation, RobustnessScorecard

UTC = timezone.utc


def _chain() -> TamperEvidentAuditChain:
    chain = TamperEvidentAuditChain()
    chain.append(GovernanceEvent.create(actor="alice", actor_role=GovernanceRole.OPERATOR, action=GovernanceAction.EVIDENCE_PACK_EXPORTED, affected_resource="evidence", reason="backup validation", severity=GovernanceSeverity.INFO, timestamp=datetime(2026, 1, 1, tzinfo=UTC)))
    return chain


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


def _ready_pack(store: InMemoryAuditStore, **ha_kwargs):
    shadow = ShadowRunValidator(store, ShadowRunGateConfig(minimum_sample_count=30, minimum_connection_uptime_pct=90, minimum_profit_factor=0, minimum_win_rate=50))
    approval = FourEyesControl().request_approval(resource="manual_review", requested_by="alice", approved_by="bob", action=GovernanceAction.MANUAL_REVIEW_COMPLETED)
    pack = EvidencePackGenerator(store, DashboardSummaryService(store), shadow).generate(config_summary={}, governance_audit_chain=_chain(), four_eyes_approvals=(approval,), **ha_kwargs)
    pack.sections["robustness_validation_json"] = {"scorecard": RobustnessScorecard(85, 90, 100, 80, 80, 80, 90, 100, 90, RobustnessRecommendation.READY_FOR_MANUAL_REVIEW, (), (), (), False).to_dict()}
    pack.sections["multi_strategy_json"] = {"allocations": {"allocations": {"A": 0.5, "B": 0.5}}, "health_scores": {"A": {"status": "HEALTHY"}, "B": {"status": "HEALTHY"}}, "overlap_warnings": ()}
    pack.sections["options_risk_json"] = {"greeks": {"data_status": "OK"}, "iv_metrics": {"data_status": "OK"}, "expiry_metrics": {"data_status": "OK"}, "concentration_metrics": {"approved": True}, "risk_warnings": (), "go_live_allowed": False}
    pack.sections["execution_realism_json"] = {"execution_reports": ({"fill_ratio": 1.0},), "latency_reports": (), "fill_ratio": 1.0, "warnings": (), "impact_warnings": (), "go_live_allowed": False}
    pack.sections["final_certification_json"] = {"certification_scorecard": {"failed_sections": (), "unavailable_sections": (), "warning_sections": (), "recommendation": "READY_FOR_MANUAL_CERTIFICATION", "go_live_allowed": False}, "readiness_report": {"critical_blockers": (), "recommendation": "READY_FOR_MANUAL_CERTIFICATION", "go_live_allowed": False}, "evidence_quality": {"acceptable": True, "go_live_allowed": False}, "review_workflow": {"completed": True, "go_live_allowed": False}, "review_board_decisions": {"completed": True, "go_live_allowed": False}, "certification_package_metadata": {"package_id": "cert-test", "go_live_allowed": False}, "go_live_allowed": False}
    return pack, shadow


def test_backup_creation_metadata_checksum_verification_and_corruption_detection(tmp_path) -> None:
    source = tmp_path / "audit.db"
    source.write_text("audit-events", encoding="utf-8")
    manager = BackupManager(tmp_path / "backups")

    metadata = manager.create_backup(source, BackupType.FULL)
    assert metadata.status == "SUCCESS"
    assert metadata.size > 0
    assert metadata.checksum
    assert manager.verify_backup(metadata).verified is True

    with open(metadata.path, "a", encoding="utf-8") as handle:
        handle.write("tamper")
    report = manager.verify_backup(metadata)
    assert report.verified is False
    assert report.corrupted_files == (metadata.path,)


def test_restore_success_and_restore_failure(tmp_path) -> None:
    source = tmp_path / "snapshot.json"
    source.write_text('{"mode":"PAPER_TRADING"}', encoding="utf-8")
    manager = BackupManager(tmp_path / "backups")
    metadata = manager.create_backup(source, BackupType.SNAPSHOT)

    restored = RestoreManager().restore(metadata, tmp_path / "restore" / "snapshot.json", manager)
    assert restored.restore_success is True
    assert restored.restored_objects

    bad = RestoreManager().restore(metadata, tmp_path / "restore2" / "snapshot.json", manager)
    # Corrupt after one successful restore to verify failure path.
    with open(metadata.path, "a", encoding="utf-8") as handle:
        handle.write("corrupt")
    failed = RestoreManager().restore(metadata, tmp_path / "restore3" / "snapshot.json", manager)
    assert bad.go_live_allowed is False
    assert failed.restore_success is False
    assert failed.errors


def test_dr_simulation_and_recovery_readiness_pass_fail(tmp_path) -> None:
    source = tmp_path / "audit.db"
    source.write_text("audit", encoding="utf-8")
    manager = BackupManager(tmp_path / "backups")
    metadata = manager.create_backup(source)
    verification = manager.verify_backup(metadata)
    restore = RestoreManager().restore(metadata, tmp_path / "restored.db", manager)
    success = DisasterRecoverySimulator().simulate(DisasterScenario.PROCESS_CRASH)
    failure = DisasterRecoverySimulator().simulate(DisasterScenario.MISSING_BACKUP, backup_available=False)

    ready = RecoveryReadinessValidator().validate(backup_metadata=metadata, verification_report=verification, restore_report=restore, recovery_reports=(success,), audit_chain=_chain())
    not_ready = RecoveryReadinessValidator().validate(backup_metadata=None, verification_report=None, restore_report=None, recovery_reports=(failure,), audit_chain=_chain())
    assert success.recovery_success is True
    assert failure.recovery_success is False
    assert ready.recommendation == RecoveryReadinessRecommendation.READY
    assert not_ready.recommendation == RecoveryReadinessRecommendation.NOT_READY


def test_retention_warning_business_continuity_and_ha_status(tmp_path) -> None:
    old = BackupManager(tmp_path / "backups").create_json_backup({"x": 1}, BackupType.AUDIT_EXPORT)
    old = old.__class__(**{**old.__dict__, "timestamp": datetime.now(UTC) - timedelta(days=400)})
    retention = BackupRetentionManager().evaluate((old,), now=datetime.now(UTC))
    assert retention.compliant is False
    assert retention.warnings

    bc = BusinessContinuityReporter().build(backup_report=None, restore_report=None, readiness_report=None, retention_report=retention, dr_reports=())
    assert bc.recommendation == BusinessContinuityRecommendation.RECOVERY_IMPROVEMENT_REQUIRED
    status = HAHealthStatus.evaluate(database_availability=True, backup_availability=False, restore_readiness=True, recovery_readiness=True, audit_chain_integrity=True, reconciliation_readiness=True, shadow_run_continuity=True)
    assert status.state == HAState.DEGRADED
    assert status.go_live_allowed is False


def test_evidence_pack_and_manual_review_gate_require_ha_dr(tmp_path) -> None:
    source = tmp_path / "audit.db"
    source.write_text("audit", encoding="utf-8")
    manager = BackupManager(tmp_path / "backups")
    metadata = manager.create_backup(source)
    verification = manager.verify_backup(metadata)
    restore = RestoreManager().restore(metadata, tmp_path / "restored.db", manager)
    dr = DisasterRecoverySimulator().simulate(DisasterScenario.RESTART_RECOVERY)
    chain = _chain()
    readiness = RecoveryReadinessValidator().validate(backup_metadata=metadata, verification_report=verification, restore_report=restore, recovery_reports=(dr,), audit_chain=chain)
    retention = BackupRetentionManager().evaluate((metadata,))
    bc = BusinessContinuityReporter().build(backup_report=verification, restore_report=restore, readiness_report=readiness, retention_report=retention, dr_reports=(dr,))
    ha = HAHealthStatus.evaluate(database_availability=True, backup_availability=True, restore_readiness=True, recovery_readiness=True, audit_chain_integrity=True, reconciliation_readiness=True, shadow_run_continuity=True)
    store = _ready_store()
    pack, shadow = _ready_pack(store, ha_status=ha, backup_reports=(verification,), restore_reports=(restore,), recovery_readiness_report=readiness, retention_compliance_report=retention, dr_simulation_reports=(dr,), business_continuity_report=bc)

    result = ManualReviewGate(min_samples=30, min_profit_factor=0, min_win_rate=50).evaluate(shadow.status(), pack, runbook_followed=True)
    assert "ha_disaster_recovery_json" in REQUIRED_EVIDENCE_SECTIONS
    assert pack.sections["ha_disaster_recovery_json"]["go_live_allowed"] is False
    assert result.decision == ManualReviewDecision.READY_FOR_MANUAL_REVIEW
    assert result.go_live_allowed is False

    missing_pack, missing_shadow = _ready_pack(store)
    missing = ManualReviewGate(min_samples=30, min_profit_factor=0, min_win_rate=50).evaluate(missing_shadow.status(), missing_pack, runbook_followed=True)
    assert missing.decision == ManualReviewDecision.CONTINUE_SHADOW
    assert "ha_dr_evidence_present" in missing.failure_reasons


def test_read_only_ha_api_live_auto_rejected_and_no_order_path() -> None:
    store = InMemoryAuditStore()
    api = ReadOnlyRuntimeAPI(store, DashboardSummaryService(store), ShadowRunValidator(store), strategy_context={"ha_status": {"state": "HEALTHY", "go_live_allowed": False}})
    assert api.ha_status()["state"] == "HEALTHY"
    assert api.ha_backups()["go_live_allowed"] is False
    assert not hasattr(api, "place_order")
    with pytest.raises(ValueError, match="rejects LIVE_AUTO"):
        RuntimeConfig(trading_mode=TradingMode.LIVE_AUTO)
