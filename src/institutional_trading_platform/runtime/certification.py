"""Final certification and human trading-desk workflow controls for Phase 20."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4

PROVENANCE_REQUIRED_KEYS = ("source_store", "event_id_range", "snapshot_id", "audit_chain_hash", "generated_at", "verification_status")


class CertificationArea(StrEnum):
    MARKET_DATA = "Market Data"
    SIGNAL_GENERATION = "Signal Generation"
    FORECASTING = "Forecasting"
    VALIDATION = "Validation"
    PAPER_TRADING = "Paper Trading"
    SHADOW_TRADING = "Shadow Trading"
    RECONCILIATION = "Reconciliation"
    PORTFOLIO_CONSTRUCTION = "Portfolio Construction"
    MULTI_STRATEGY_LAYER = "Multi-Strategy Layer"
    OPTIONS_RISK = "Options Risk"
    EXECUTION_REALISM = "Execution Realism"
    MONITORING = "Monitoring"
    GOVERNANCE = "Governance"
    COMPLIANCE = "Compliance"
    HA_DR = "HA/DR"
    EVIDENCE_QUALITY = "Evidence Quality"


class CertificationStatus(StrEnum):
    PASS = "PASS"
    PASS_WITH_WARNINGS = "PASS_WITH_WARNINGS"
    FAIL = "FAIL"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"


class CertificationRecommendation(StrEnum):
    CONTINUE_SHADOW = "CONTINUE_SHADOW"
    BLOCKED_FOR_REVIEW = "BLOCKED_FOR_REVIEW"
    READY_FOR_MANUAL_CERTIFICATION = "READY_FOR_MANUAL_CERTIFICATION"


@dataclass(frozen=True)
class CertificationAreaReport:
    area: CertificationArea
    status: CertificationStatus
    evidence_keys: tuple[str, ...]
    warnings: tuple[str, ...] = ()
    failures: tuple[str, ...] = ()
    go_live_allowed: bool = False

    def to_dict(self) -> dict[str, object]:
        return {**asdict(self), "area": self.area.value, "status": self.status.value, "go_live_allowed": False}


@dataclass(frozen=True)
class CertificationScorecard:
    passed_sections: tuple[str, ...]
    warning_sections: tuple[str, ...]
    failed_sections: tuple[str, ...]
    unavailable_sections: tuple[str, ...]
    total_sections: int
    completion_percentage: float
    recommendation: CertificationRecommendation
    go_live_allowed: bool = False

    def to_dict(self) -> dict[str, object]:
        return {**asdict(self), "recommendation": self.recommendation.value, "go_live_allowed": False}


class FinalCertificationFramework:
    AREA_EVIDENCE: dict[CertificationArea, tuple[str, ...]] = {
        CertificationArea.MARKET_DATA: ("audit_events_json",),
        CertificationArea.SIGNAL_GENERATION: ("shadow_run_status_json",),
        CertificationArea.FORECASTING: ("research_ml_json",),
        CertificationArea.VALIDATION: ("validation_report_json", "robustness_validation_json"),
        CertificationArea.PAPER_TRADING: ("runtime_snapshot_json",),
        CertificationArea.SHADOW_TRADING: ("shadow_run_status_json",),
        CertificationArea.RECONCILIATION: ("reconciliation_summary_json",),
        CertificationArea.PORTFOLIO_CONSTRUCTION: ("multi_strategy_json",),
        CertificationArea.MULTI_STRATEGY_LAYER: ("multi_strategy_json",),
        CertificationArea.OPTIONS_RISK: ("options_risk_json",),
        CertificationArea.EXECUTION_REALISM: ("execution_realism_json",),
        CertificationArea.MONITORING: ("monitoring_json",),
        CertificationArea.GOVERNANCE: ("governance_compliance_json",),
        CertificationArea.COMPLIANCE: ("governance_compliance_json",),
        CertificationArea.HA_DR: ("ha_disaster_recovery_json",),
        CertificationArea.EVIDENCE_QUALITY: ("safety_report_json",),
    }

    def certify(self, evidence_sections: dict[str, object]) -> tuple[CertificationAreaReport, ...]:
        return tuple(self.certify_area(area, evidence_sections) for area in CertificationArea)

    def certify_area(self, area: CertificationArea, evidence_sections: dict[str, object]) -> CertificationAreaReport:
        keys = self.AREA_EVIDENCE[area]
        missing = tuple(key for key in keys if key not in evidence_sections or evidence_sections.get(key) in ({}, None))
        if missing:
            return CertificationAreaReport(area, CertificationStatus.DATA_UNAVAILABLE, keys, failures=tuple(f"missing {key}" for key in missing), go_live_allowed=False)
        warnings: list[str] = []
        failures: list[str] = []
        for key in keys:
            section = evidence_sections[key]
            if isinstance(section, dict):
                provenance = section.get("provenance")
                if not isinstance(provenance, dict):
                    failures.append(f"{key} missing provenance")
                else:
                    missing_provenance = tuple(item for item in PROVENANCE_REQUIRED_KEYS if provenance.get(item) in (None, "", (), "DATA_UNAVAILABLE"))
                    if missing_provenance:
                        failures.append(f"{key} provenance unavailable: {', '.join(missing_provenance)}")
                if section.get("data_status") == "DATA_UNAVAILABLE":
                    failures.append(f"{key} data unavailable")
                if section.get("go_live_allowed") is True:
                    failures.append(f"{key} attempted go_live_allowed=true")
                warnings.extend(str(item) for item in section.get("warnings", ()) if item)
                warnings.extend(str(item) for item in section.get("risk_warnings", ()) if item)
                if key == "governance_compliance_json" and section.get("unresolved_governance_blocks"):
                    failures.append("unresolved governance block")
                if key == "ha_disaster_recovery_json" and section.get("data_status") == "DATA_UNAVAILABLE":
                    failures.append("HA/DR evidence unavailable")
        status = CertificationStatus.FAIL if failures else (CertificationStatus.PASS_WITH_WARNINGS if warnings else CertificationStatus.PASS)
        return CertificationAreaReport(area, status, keys, tuple(warnings), tuple(failures), False)

    def scorecard(self, reports: tuple[CertificationAreaReport, ...]) -> CertificationScorecard:
        passed = tuple(report.area.value for report in reports if report.status == CertificationStatus.PASS)
        warned = tuple(report.area.value for report in reports if report.status == CertificationStatus.PASS_WITH_WARNINGS)
        failed = tuple(report.area.value for report in reports if report.status == CertificationStatus.FAIL)
        unavailable = tuple(report.area.value for report in reports if report.status == CertificationStatus.DATA_UNAVAILABLE)
        total = len(reports)
        completion = round(100.0 * (len(passed) + len(warned)) / total, 2) if total else 0.0
        recommendation = CertificationRecommendation.READY_FOR_MANUAL_CERTIFICATION if not failed and not unavailable else (CertificationRecommendation.BLOCKED_FOR_REVIEW if failed else CertificationRecommendation.CONTINUE_SHADOW)
        return CertificationScorecard(passed, warned, failed, unavailable, total, completion, recommendation, False)


class ReviewStageStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ReviewBoardRole(StrEnum):
    ANALYST = "ANALYST"
    RISK_MANAGER = "RISK_MANAGER"
    OPERATIONS_MANAGER = "OPERATIONS_MANAGER"
    COMPLIANCE_REVIEWER = "COMPLIANCE_REVIEWER"
    FINAL_REVIEWER = "FINAL_REVIEWER"


@dataclass(frozen=True)
class ReviewDecision:
    role: ReviewBoardRole
    status: ReviewStageStatus
    reviewer: str
    timestamp: datetime
    notes: str = ""
    rejection_reason: str = ""
    go_live_allowed: bool = False

    def to_dict(self) -> dict[str, object]:
        return {**asdict(self), "role": self.role.value, "status": self.status.value, "timestamp": self.timestamp.isoformat(), "go_live_allowed": False}


class ReviewBoard:
    REQUIRED_ROLES = tuple(ReviewBoardRole)

    def __init__(self) -> None:
        self.decisions: dict[ReviewBoardRole, ReviewDecision] = {}

    def record_decision(self, role: ReviewBoardRole, status: ReviewStageStatus, *, reviewer: str, notes: str = "", rejection_reason: str = "", timestamp: datetime | None = None) -> ReviewDecision:
        if status == ReviewStageStatus.REJECTED and not rejection_reason:
            rejection_reason = "review rejected"
        decision = ReviewDecision(role, status, reviewer, timestamp or datetime.now(timezone.utc), notes, rejection_reason, False)
        self.decisions[role] = decision
        return decision

    @property
    def completed(self) -> bool:
        return all(self.decisions.get(role) and self.decisions[role].status == ReviewStageStatus.APPROVED for role in self.REQUIRED_ROLES)

    def to_dict(self) -> dict[str, object]:
        return {"decisions": tuple(decision.to_dict() for decision in self.decisions.values()), "completed": self.completed, "go_live_allowed": False}


class TradingDeskWorkflow:
    def __init__(self, board: ReviewBoard | None = None) -> None:
        self.board = board or ReviewBoard()

    def analyst_review(self, reviewer: str, approved: bool, notes: str = "") -> ReviewDecision:
        return self.board.record_decision(ReviewBoardRole.ANALYST, ReviewStageStatus.APPROVED if approved else ReviewStageStatus.REJECTED, reviewer=reviewer, notes=notes, rejection_reason="analyst rejected" if not approved else "")

    def risk_review(self, reviewer: str, approved: bool, notes: str = "") -> ReviewDecision:
        return self.board.record_decision(ReviewBoardRole.RISK_MANAGER, ReviewStageStatus.APPROVED if approved else ReviewStageStatus.REJECTED, reviewer=reviewer, notes=notes, rejection_reason="risk rejected" if not approved else "")

    def operations_review(self, reviewer: str, approved: bool, notes: str = "") -> ReviewDecision:
        return self.board.record_decision(ReviewBoardRole.OPERATIONS_MANAGER, ReviewStageStatus.APPROVED if approved else ReviewStageStatus.REJECTED, reviewer=reviewer, notes=notes, rejection_reason="operations rejected" if not approved else "")

    def compliance_review(self, reviewer: str, approved: bool, notes: str = "") -> ReviewDecision:
        return self.board.record_decision(ReviewBoardRole.COMPLIANCE_REVIEWER, ReviewStageStatus.APPROVED if approved else ReviewStageStatus.REJECTED, reviewer=reviewer, notes=notes, rejection_reason="compliance rejected" if not approved else "")

    def final_signoff(self, reviewer: str, approved: bool, notes: str = "") -> ReviewDecision:
        return self.board.record_decision(ReviewBoardRole.FINAL_REVIEWER, ReviewStageStatus.APPROVED if approved else ReviewStageStatus.REJECTED, reviewer=reviewer, notes=notes, rejection_reason="final reviewer rejected" if not approved else "")

    def to_dict(self) -> dict[str, object]:
        return self.board.to_dict()


@dataclass(frozen=True)
class EvidenceQualityReport:
    evidence_complete: bool
    missing_reports: tuple[str, ...]
    stale_reports: tuple[str, ...]
    missing_shadow_data: bool
    missing_robustness_data: bool
    missing_monitoring_data: bool
    missing_compliance_data: bool
    acceptable: bool
    go_live_allowed: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self) | {"go_live_allowed": False}


class EvidenceQualityValidator:
    def validate(self, evidence_sections: dict[str, object], required_sections: tuple[str, ...], *, stale_sections: tuple[str, ...] = ()) -> EvidenceQualityReport:
        missing = tuple(key for key in required_sections if key not in evidence_sections or evidence_sections.get(key) in ({}, None) or (isinstance(evidence_sections.get(key), dict) and evidence_sections[key].get("data_status") == "DATA_UNAVAILABLE"))
        return EvidenceQualityReport(
            evidence_complete=not missing,
            missing_reports=missing,
            stale_reports=stale_sections,
            missing_shadow_data="shadow_run_status_json" in missing,
            missing_robustness_data="robustness_validation_json" in missing,
            missing_monitoring_data="monitoring_json" in missing,
            missing_compliance_data="governance_compliance_json" in missing,
            acceptable=not missing and not stale_sections,
            go_live_allowed=False,
        )


@dataclass(frozen=True)
class FinalReadinessReport:
    certification_scorecard: CertificationScorecard
    compliance_status: str
    monitoring_status: str
    robustness_status: str
    execution_realism_status: str
    governance_status: str
    ha_dr_status: str
    shadow_run_status: str
    unresolved_issues: tuple[str, ...]
    critical_blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    recommendation: CertificationRecommendation
    go_live_allowed: bool = False

    def to_dict(self) -> dict[str, object]:
        return {**asdict(self), "certification_scorecard": self.certification_scorecard.to_dict(), "recommendation": self.recommendation.value, "go_live_allowed": False}


class FinalReadinessReporter:
    def build(self, scorecard: CertificationScorecard, evidence_quality: EvidenceQualityReport) -> FinalReadinessReport:
        critical = tuple(scorecard.failed_sections) + tuple(evidence_quality.missing_reports)
        warnings = tuple(scorecard.warning_sections) + tuple(evidence_quality.stale_reports)
        recommendation = CertificationRecommendation.READY_FOR_MANUAL_CERTIFICATION if scorecard.recommendation == CertificationRecommendation.READY_FOR_MANUAL_CERTIFICATION and evidence_quality.acceptable else CertificationRecommendation.BLOCKED_FOR_REVIEW
        return FinalReadinessReport(scorecard, "PASS" if "Compliance" not in critical else "FAIL", "PASS" if "Monitoring" not in critical else "FAIL", "PASS" if "Validation" not in critical else "FAIL", "PASS" if "Execution Realism" not in critical else "FAIL", "PASS" if "Governance" not in critical else "FAIL", "PASS" if "HA/DR" not in critical else "FAIL", "PASS" if "Shadow Trading" not in critical else "FAIL", tuple(evidence_quality.missing_reports), critical, warnings, recommendation, False)


class FinalChecklistRecommendation(StrEnum):
    READY_FOR_MANUAL_CERTIFICATION = "READY_FOR_MANUAL_CERTIFICATION"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class FinalOperationalChecklist:
    shadow_run_complete: bool
    reconciliation_clean: bool
    no_critical_incidents: bool
    governance_pass: bool
    compliance_pass: bool
    audit_chain_valid: bool
    backup_verified: bool
    restore_tested: bool
    robustness_pass: bool
    execution_realism_pass: bool
    monitoring_pass: bool
    evidence_complete: bool
    recommendation: FinalChecklistRecommendation
    go_live_allowed: bool = False

    def to_dict(self) -> dict[str, object]:
        return {**asdict(self), "recommendation": self.recommendation.value, "go_live_allowed": False}

    @classmethod
    def build(cls, **checks: bool) -> "FinalOperationalChecklist":
        fields = {name: bool(checks.get(name, False)) for name in ("shadow_run_complete", "reconciliation_clean", "no_critical_incidents", "governance_pass", "compliance_pass", "audit_chain_valid", "backup_verified", "restore_tested", "robustness_pass", "execution_realism_pass", "monitoring_pass", "evidence_complete")}
        recommendation = FinalChecklistRecommendation.READY_FOR_MANUAL_CERTIFICATION if all(fields.values()) else FinalChecklistRecommendation.BLOCKED
        return cls(**fields, recommendation=recommendation, go_live_allowed=False)


@dataclass(frozen=True)
class ManualCertificationPackage:
    package_id: str
    created_at: datetime
    executive_summary: str
    certification_scorecard: CertificationScorecard
    readiness_report: FinalReadinessReport
    evidence_summary: dict[str, object]
    compliance_summary: dict[str, object]
    governance_summary: dict[str, object]
    risk_summary: dict[str, object]
    unresolved_items: tuple[str, ...]
    go_live_allowed: bool = False

    @property
    def metadata(self) -> dict[str, object]:
        return {"package_id": self.package_id, "created_at": self.created_at.isoformat(), "recommendation": self.readiness_report.recommendation.value, "go_live_allowed": False}

    def to_json_metadata(self) -> str:
        return json.dumps(self.metadata, indent=2, sort_keys=True)

    def to_markdown(self) -> str:
        return f"# Manual Certification Package\n\nRecommendation: {self.readiness_report.recommendation.value}\n\nGo live allowed: false\n\n{self.executive_summary}"


class ManualCertificationPackageGenerator:
    def generate(self, scorecard: CertificationScorecard, readiness: FinalReadinessReport, *, evidence_summary: dict[str, object], compliance_summary: dict[str, object], governance_summary: dict[str, object], risk_summary: dict[str, object]) -> ManualCertificationPackage:
        summary = "Manual certification package is for human review only and does not authorize LIVE_AUTO."
        return ManualCertificationPackage(f"cert-{uuid4()}", datetime.now(timezone.utc), summary, scorecard, readiness, evidence_summary, compliance_summary, governance_summary, risk_summary, readiness.critical_blockers, False)


def final_certification_evidence_section(*, scorecard: CertificationScorecard | None = None, readiness_report: FinalReadinessReport | None = None, evidence_quality: EvidenceQualityReport | None = None, workflow: TradingDeskWorkflow | None = None, review_board: ReviewBoard | None = None, certification_package: ManualCertificationPackage | None = None) -> dict[str, object]:
    if scorecard is None or readiness_report is None or evidence_quality is None or certification_package is None:
        return {"data_status": "DATA_UNAVAILABLE", "go_live_allowed": False}
    board = review_board or (workflow.board if workflow is not None else ReviewBoard())
    return {
        "certification_scorecard": scorecard.to_dict(),
        "readiness_report": readiness_report.to_dict(),
        "evidence_quality": evidence_quality.to_dict(),
        "review_workflow": workflow.to_dict() if workflow else {"completed": board.completed, "go_live_allowed": False},
        "review_board_decisions": board.to_dict(),
        "certification_package_metadata": certification_package.metadata,
        "go_live_allowed": False,
    }
