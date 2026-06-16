"""Evidence pack exports for Phase 10 shadow/manual review."""

from __future__ import annotations

import json
import hashlib
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from uuid import uuid4

from .audit_store import InMemoryAuditStore
from .dashboard import DashboardSummaryService
from .daily_report import DailyShadowReport
from .shadow_run import ShadowRunValidator
from ..validation.robustness import RobustnessReport, RobustnessScorecard
from .security import redact_secrets
from ..strategy_orchestration import StrategyAllocationReport, StrategyCorrelationReport, StrategyHealthScore, StrategyRegimeCompatibility, StrategyRegistry, UnifiedSignalDecision, multi_strategy_evidence_section
from ..derivatives import FORiskReport, IVAnalysis, ExpiryRiskReport, GapRiskReport, options_risk_evidence_section
from ..execution_simulation import ExecutionQualityReport, execution_realism_evidence_section
from ..research_ml import ResearchMLReport, research_ml_evidence_section
from .monitoring import AlertRouter, IncidentManager, MetricsRegistry, SLOStatus, monitoring_evidence_section
from .governance import ComplianceChecklistReport, FourEyesApproval, PolicyViolation, RoleBasedAccessControl, TamperEvidentAuditChain, governance_compliance_evidence_section
from .ha_dr import HAHealthStatus, BackupVerificationReport, RestoreReport, RecoveryReadinessReport, RetentionComplianceReport, DisasterRecoveryReport, BusinessContinuityReport, ha_disaster_recovery_evidence_section
from .certification import CertificationScorecard, EvidenceQualityReport, FinalReadinessReport, ManualCertificationPackage, ReviewBoard, TradingDeskWorkflow, final_certification_evidence_section


REQUIRED_EVIDENCE_SECTIONS = (
    "audit_events_json",
    "runtime_snapshot_json",
    "shadow_run_status_json",
    "validation_report_json",
    "dashboard_summary_json",
    "reconciliation_summary_json",
    "risk_summary_json",
    "alerts_json",
    "config_profile_summary_json",
    "safety_report_json",
    "markdown_executive_summary",
    "robustness_validation_json",
    "multi_strategy_json",
    "options_risk_json",
    "execution_realism_json",
    "research_ml_json",
    "monitoring_json",
    "governance_compliance_json",
    "ha_disaster_recovery_json",
    "final_certification_json",
)

PROVENANCE_REQUIRED_KEYS = ("source_store", "event_id_range", "snapshot_id", "audit_chain_hash", "generated_at", "verification_status")


@dataclass(frozen=True)
class EvidencePack:
    pack_id: str
    created_at: datetime
    sections: dict[str, object]
    go_live_allowed: bool = False

    @property
    def metadata(self) -> dict[str, object]:
        return {"pack_id": self.pack_id, "created_at": self.created_at.isoformat(), "sections": tuple(self.sections), "go_live_allowed": False}

    def to_json(self) -> str:
        return json.dumps(redact_secrets({"metadata": self.metadata, "sections": self.sections}), indent=2, sort_keys=True, default=str)


class EvidencePackGenerator:
    """Build exportable evidence from durable audit/runtime services."""

    def __init__(self, audit_store: InMemoryAuditStore, dashboard: DashboardSummaryService, shadow: ShadowRunValidator) -> None:
        self.audit_store = audit_store
        self.dashboard = dashboard
        self.shadow = shadow

    def generate(self, *, config_summary: dict[str, object], validation_report: object | None = None, daily_report: DailyShadowReport | None = None, robustness_report: RobustnessReport | None = None, robustness_scorecard: RobustnessScorecard | None = None, strategy_registry: StrategyRegistry | None = None, strategy_health_scores: dict[str, StrategyHealthScore] | None = None, strategy_allocation_report: StrategyAllocationReport | None = None, strategy_correlation_report: StrategyCorrelationReport | None = None, strategy_regime_scores: tuple[StrategyRegimeCompatibility, ...] = (), unified_decisions: tuple[UnifiedSignalDecision, ...] = (), options_risk_report: FORiskReport | None = None, options_iv_analysis: IVAnalysis | None = None, options_expiry_report: ExpiryRiskReport | None = None, options_gap_report: GapRiskReport | None = None, execution_reports: tuple[ExecutionQualityReport, ...] = (), execution_assumptions: dict[str, object] | None = None, research_ml_report: ResearchMLReport | None = None, metrics_registry: MetricsRegistry | None = None, incident_manager: IncidentManager | None = None, slo_status: SLOStatus | None = None, alert_router: AlertRouter | None = None, governance_audit_chain: TamperEvidentAuditChain | None = None, governance_rbac: RoleBasedAccessControl | None = None, policy_violations: tuple[PolicyViolation, ...] = (), compliance_report: ComplianceChecklistReport | None = None, four_eyes_approvals: tuple[FourEyesApproval, ...] = (), ha_status: HAHealthStatus | None = None, backup_reports: tuple[BackupVerificationReport, ...] = (), restore_reports: tuple[RestoreReport, ...] = (), recovery_readiness_report: RecoveryReadinessReport | None = None, retention_compliance_report: RetentionComplianceReport | None = None, dr_simulation_reports: tuple[DisasterRecoveryReport, ...] = (), business_continuity_report: BusinessContinuityReport | None = None, certification_scorecard: CertificationScorecard | None = None, final_readiness_report: FinalReadinessReport | None = None, evidence_quality_report: EvidenceQualityReport | None = None, trading_desk_workflow: TradingDeskWorkflow | None = None, review_board: ReviewBoard | None = None, manual_certification_package: ManualCertificationPackage | None = None) -> EvidencePack:
        events = self.audit_store.all_events()
        snapshot = self.audit_store.latest_snapshot() if hasattr(self.audit_store, "latest_snapshot") else None
        generated_at = datetime.now(timezone.utc)
        provenance = self._provenance(events, snapshot, generated_at)
        shadow_status = self.shadow.status()
        dashboard_summary = self.dashboard.summary()
        reconciliation_events = [event.payload for event in events if event.event_type.value.startswith("BrokerReconciliation")]
        risk_events = [event.payload for event in events if event.event_type.value == "RiskBlocked"]
        alerts = [event.payload for event in events if event.event_type.value == "AlertEmitted"]
        robustness_section = self._robustness_section(robustness_report, robustness_scorecard)
        multi_strategy_section = self._multi_strategy_section(strategy_registry, strategy_health_scores, strategy_allocation_report, strategy_correlation_report, strategy_regime_scores, unified_decisions)
        options_section = self._options_section(options_risk_report, options_iv_analysis, options_expiry_report, options_gap_report)
        execution_section = self._execution_section(execution_reports, execution_assumptions)
        research_ml_section = research_ml_evidence_section(research_ml_report)
        monitoring_section = monitoring_evidence_section(metrics_registry, incident_manager, slo_status, alert_router)
        governance_section = governance_compliance_evidence_section(audit_chain=governance_audit_chain, rbac=governance_rbac, policy_violations=policy_violations, compliance_report=compliance_report, four_eyes_approvals=four_eyes_approvals)
        ha_dr_section = ha_disaster_recovery_evidence_section(ha_status=ha_status, backup_reports=backup_reports, restore_reports=restore_reports, recovery_readiness=recovery_readiness_report, retention_compliance=retention_compliance_report, dr_simulations=dr_simulation_reports, business_continuity_report=business_continuity_report)
        final_certification_section = final_certification_evidence_section(scorecard=certification_scorecard, readiness_report=final_readiness_report, evidence_quality=evidence_quality_report, workflow=trading_desk_workflow, review_board=review_board, certification_package=manual_certification_package)
        safety = {
            "go_live_allowed": False,
            "live_auto_ready": False,
            "real_order_placement_enabled": False,
            "unsafe_real_order_attempts": len([event for event in events if event.event_type.value == "RealOrderBlocked"]),
            "manual_review_required": True,
        }
        raw_sections = {
            "audit_events_json": json.loads(self.audit_store.export_json()),
            "runtime_snapshot_json": asdict(snapshot) if snapshot is not None else {},
            "shadow_run_status_json": asdict(shadow_status),
            "validation_report_json": validation_report if validation_report is not None else {},
            "dashboard_summary_json": asdict(dashboard_summary),
            "reconciliation_summary_json": {"events": reconciliation_events},
            "risk_summary_json": {"risk_events": risk_events},
            "alerts_json": alerts,
            "config_profile_summary_json": redact_secrets(config_summary),
            "safety_report_json": safety,
            "markdown_executive_summary": self._markdown(shadow_status.recommendation.value, daily_report, safety),
            "robustness_validation_json": robustness_section,
            "multi_strategy_json": multi_strategy_section,
            "options_risk_json": options_section,
            "execution_realism_json": execution_section,
            "research_ml_json": research_ml_section,
            "monitoring_json": monitoring_section,
            "governance_compliance_json": governance_section,
            "ha_disaster_recovery_json": ha_dr_section,
            "final_certification_json": final_certification_section,
        }
        sections = {name: self._with_provenance(value, provenance) for name, value in raw_sections.items()}
        return EvidencePack(f"evidence-{uuid4()}", generated_at, sections, False)

    def _provenance(self, events: tuple[object, ...], snapshot: object | None, generated_at: datetime) -> dict[str, object]:
        event_ids = tuple(getattr(event, "event_id", "") for event in events if getattr(event, "event_id", ""))
        source_store = f"{self.audit_store.__class__.__module__}.{self.audit_store.__class__.__name__}"
        snapshot_id = getattr(snapshot, "snapshot_id", None)
        chain_material = json.dumps({"events": event_ids, "snapshot_id": snapshot_id, "source_store": source_store}, sort_keys=True, default=str).encode("utf-8")
        verification_status = "VERIFIED" if event_ids else "DATA_UNAVAILABLE"
        return {
            "source_store": source_store,
            "event_id_range": (event_ids[0], event_ids[-1]) if event_ids else (),
            "snapshot_id": snapshot_id or "NOT_APPLICABLE",
            "audit_chain_hash": hashlib.sha256(chain_material).hexdigest() if event_ids else "DATA_UNAVAILABLE",
            "generated_at": generated_at.isoformat(),
            "verification_status": verification_status,
        }

    @staticmethod
    def _with_provenance(value: object, provenance: dict[str, object]) -> dict[str, object]:
        status = "OK" if provenance["verification_status"] == "VERIFIED" else "DATA_UNAVAILABLE"
        if isinstance(value, dict):
            return {**value, "provenance": provenance, "data_status": value.get("data_status", status)}
        return {"data": value, "provenance": provenance, "data_status": status, "go_live_allowed": False}

    @staticmethod
    def _execution_section(reports: tuple[ExecutionQualityReport, ...], assumptions: dict[str, object] | None) -> dict[str, object]:
        if reports:
            return execution_realism_evidence_section(reports, assumptions)
        return {
            "execution_reports": (),
            "latency_reports": (),
            "slippage_assumptions": assumptions or {},
            "impact_warnings": ("execution realism evidence unavailable",),
            "fill_realism_score": 0.0,
            "fill_ratio": 0.0,
            "warnings": ("missing execution quality reports",),
            "go_live_allowed": False,
        }

    @staticmethod
    def _options_section(risk_report: FORiskReport | None, iv_analysis: IVAnalysis | None, expiry_report: ExpiryRiskReport | None, gap_report: GapRiskReport | None) -> dict[str, object]:
        if risk_report is not None and iv_analysis is not None and expiry_report is not None and gap_report is not None:
            return options_risk_evidence_section(risk_report, iv_analysis, expiry_report, gap_report)
        return {
            "greeks": {},
            "iv_metrics": {},
            "expiry_metrics": {},
            "concentration_metrics": {},
            "gap_risk": {},
            "risk_warnings": ("options risk evidence unavailable",),
            "go_live_allowed": False,
        }

    @staticmethod
    def _multi_strategy_section(strategy_registry: StrategyRegistry | None, health_scores: dict[str, StrategyHealthScore] | None, allocation_report: StrategyAllocationReport | None, correlation_report: StrategyCorrelationReport | None, regime_scores: tuple[StrategyRegimeCompatibility, ...], unified_decisions: tuple[UnifiedSignalDecision, ...]) -> dict[str, object]:
        if strategy_registry and health_scores is not None and allocation_report is not None and correlation_report is not None:
            return multi_strategy_evidence_section(strategy_registry, health_scores, allocation_report, correlation_report, regime_scores, unified_decisions)
        return {
            "registered_strategies": (),
            "health_scores": {},
            "allocations": {},
            "correlation_matrix": {},
            "overlap_warnings": ("multi-strategy evidence unavailable",),
            "regime_compatibility": (),
            "unified_decisions": (),
            "conflict_reports": (),
            "go_live_allowed": False,
        }

    @staticmethod
    def _robustness_section(robustness_report: RobustnessReport | None, robustness_scorecard: RobustnessScorecard | None) -> dict[str, object]:
        if robustness_report is not None:
            return robustness_report.to_dict()
        if robustness_scorecard is not None:
            return {"scorecard": robustness_scorecard.to_dict(), "failed_robustness_checks": robustness_scorecard.failed_checks, "overfitting_warnings": robustness_scorecard.warnings + robustness_scorecard.critical_flags}
        return {
            "scorecard": None,
            "failed_robustness_checks": ("robustness evidence unavailable",),
            "regime_report": {},
            "symbol_concentration_report": {},
            "timeframe_report": {},
            "parameter_sensitivity_report": (),
            "overfitting_warnings": ("missing Phase 11 robustness scorecard",),
            "go_live_allowed": False,
        }

    @staticmethod
    def _markdown(recommendation: str, daily_report: DailyShadowReport | None, safety: dict[str, object]) -> str:
        lines = ["# ALPHA-GATE X Shadow Evidence Pack", "", f"Recommendation: **{recommendation}**", f"Go-live allowed: **{safety['go_live_allowed']}**", "", "No LIVE_AUTO or real order placement is authorized."]
        if daily_report is not None:
            lines.extend(["", f"Daily report date: {daily_report.trading_day.isoformat()}", f"Signals: {daily_report.signals_generated}", f"Blocked orders: {daily_report.blocked_order_attempts}"])
        return "\n".join(lines)
