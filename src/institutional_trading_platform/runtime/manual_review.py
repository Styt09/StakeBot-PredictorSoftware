"""Manual review gate for Phase 10 shadow evidence."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .evidence_pack import EvidencePack
from ..validation.robustness import RobustnessRecommendation, RobustnessScorecard
from .shadow_run import ShadowRunStatus


class ManualReviewDecision(StrEnum):
    CONTINUE_SHADOW = "CONTINUE_SHADOW"
    BLOCKED_FOR_REVIEW = "BLOCKED_FOR_REVIEW"
    READY_FOR_MANUAL_REVIEW = "READY_FOR_MANUAL_REVIEW"


@dataclass(frozen=True)
class ManualReviewChecklist:
    trading_days_complete: bool
    sufficient_samples: bool
    no_unresolved_reconciliation_drift: bool
    zero_unsafe_real_order_attempts: bool
    data_quality_acceptable: bool
    feed_freshness_acceptable: bool
    drawdown_within_limit: bool
    profit_factor_threshold_met: bool
    win_rate_threshold_met: bool
    operational_runbook_followed: bool
    evidence_pack_exported: bool
    robustness_score_passed: bool
    no_critical_overfitting_flags: bool
    oos_walk_forward_evidence_exists: bool
    execution_realism_passed: bool
    regime_stability_passed: bool
    strategy_diversification_acceptable: bool
    strategy_correlation_acceptable: bool
    strategy_health_acceptable: bool
    no_disabled_strategy_dominating: bool
    options_greeks_acceptable: bool
    options_concentration_acceptable: bool
    options_expiry_risk_acceptable: bool
    options_iv_exposure_acceptable: bool
    execution_realism_evidence_present: bool
    execution_fill_ratio_acceptable: bool
    execution_slippage_acceptable: bool
    execution_market_impact_acceptable: bool
    execution_latency_acceptable: bool
    no_critical_impossible_fill_warnings: bool
    monitoring_evidence_present: bool
    no_unresolved_critical_incidents: bool
    slo_targets_acceptable: bool
    alert_routing_configured: bool
    governance_compliance_evidence_present: bool
    audit_chain_valid: bool
    no_unresolved_critical_policy_violation: bool
    four_eyes_signoff_present: bool
    compliance_checklist_passed: bool
    ha_dr_evidence_present: bool
    backup_verified: bool
    restore_tested: bool
    ha_audit_chain_valid: bool
    recovery_readiness_ready: bool
    retention_compliant: bool
    no_unresolved_dr_failure: bool
    certification_package_present: bool
    evidence_quality_acceptable: bool
    review_workflow_completed: bool
    no_critical_certification_failure: bool
    certification_governance_compliance_pass: bool
    certification_ha_dr_pass: bool
    human_reviewer_signoff_required: bool = True
    go_live_allowed: bool = False


@dataclass(frozen=True)
class ManualReviewGateResult:
    decision: ManualReviewDecision
    checklist: ManualReviewChecklist
    failure_reasons: tuple[str, ...]
    go_live_allowed: bool = False


class ManualReviewGate:
    """Evaluate manual-review readiness. Never returns LIVE_AUTO readiness."""

    def __init__(self, *, min_days: int = 30, min_samples: int = 100, max_drawdown: float = 15.0, min_profit_factor: float = 1.5, min_win_rate: float = 50.0, max_data_quality_failures: int = 5, max_stale_incidents: int = 5) -> None:
        self.min_days = min_days
        self.min_samples = min_samples
        self.max_drawdown = max_drawdown
        self.min_profit_factor = min_profit_factor
        self.min_win_rate = min_win_rate
        self.max_data_quality_failures = max_data_quality_failures
        self.max_stale_incidents = max_stale_incidents

    def evaluate(self, status: ShadowRunStatus, evidence_pack: EvidencePack | None, *, runbook_followed: bool = False, robustness_scorecard: RobustnessScorecard | None = None) -> ManualReviewGateResult:
        metrics = status.win_loss_metrics
        scorecard = robustness_scorecard or self._scorecard_from_evidence(evidence_pack)
        robustness_pass = bool(scorecard and scorecard.overall_score >= 70.0 and scorecard.recommendation == RobustnessRecommendation.READY_FOR_MANUAL_REVIEW)
        no_critical = bool(scorecard and not scorecard.critical_flags)
        oos_walk_forward = bool(scorecard and "missing out-of-sample evidence" not in scorecard.failed_checks and "missing walk-forward evidence" not in scorecard.failed_checks)
        execution_pass = bool(scorecard and scorecard.execution_realism_score >= 70.0)
        regime_pass = bool(scorecard and scorecard.regime_stability_score >= 50.0)
        strategy_checks = self._multi_strategy_checks(evidence_pack)
        options_checks = self._options_checks(evidence_pack)
        execution_checks = self._execution_checks(evidence_pack)
        monitoring_checks = self._monitoring_checks(evidence_pack)
        governance_checks = self._governance_checks(evidence_pack)
        ha_dr_checks = self._ha_dr_checks(evidence_pack)
        certification_checks = self._certification_checks(evidence_pack)
        checklist = ManualReviewChecklist(
            trading_days_complete=status.trading_days_completed >= self.min_days,
            sufficient_samples=status.total_signals >= self.min_samples,
            no_unresolved_reconciliation_drift=status.reconciliation_failures == 0,
            zero_unsafe_real_order_attempts=status.blocked_orders_count == 0,
            data_quality_acceptable=status.data_quality_failures <= self.max_data_quality_failures,
            feed_freshness_acceptable=status.stale_feed_incidents <= self.max_stale_incidents,
            drawdown_within_limit=status.max_paper_drawdown <= self.max_drawdown,
            profit_factor_threshold_met=float(metrics.get("profit_factor", 0.0)) >= self.min_profit_factor,
            win_rate_threshold_met=float(metrics.get("win_rate", 0.0)) >= self.min_win_rate,
            operational_runbook_followed=runbook_followed,
            evidence_pack_exported=evidence_pack is not None,
            robustness_score_passed=robustness_pass,
            no_critical_overfitting_flags=no_critical,
            oos_walk_forward_evidence_exists=oos_walk_forward,
            execution_realism_passed=execution_pass,
            regime_stability_passed=regime_pass,
            strategy_diversification_acceptable=strategy_checks["strategy_diversification_acceptable"],
            strategy_correlation_acceptable=strategy_checks["strategy_correlation_acceptable"],
            strategy_health_acceptable=strategy_checks["strategy_health_acceptable"],
            no_disabled_strategy_dominating=strategy_checks["no_disabled_strategy_dominating"],
            options_greeks_acceptable=options_checks["options_greeks_acceptable"],
            options_concentration_acceptable=options_checks["options_concentration_acceptable"],
            options_expiry_risk_acceptable=options_checks["options_expiry_risk_acceptable"],
            options_iv_exposure_acceptable=options_checks["options_iv_exposure_acceptable"],
            execution_realism_evidence_present=execution_checks["execution_realism_evidence_present"],
            execution_fill_ratio_acceptable=execution_checks["execution_fill_ratio_acceptable"],
            execution_slippage_acceptable=execution_checks["execution_slippage_acceptable"],
            execution_market_impact_acceptable=execution_checks["execution_market_impact_acceptable"],
            execution_latency_acceptable=execution_checks["execution_latency_acceptable"],
            no_critical_impossible_fill_warnings=execution_checks["no_critical_impossible_fill_warnings"],
            monitoring_evidence_present=monitoring_checks["monitoring_evidence_present"],
            no_unresolved_critical_incidents=monitoring_checks["no_unresolved_critical_incidents"],
            slo_targets_acceptable=monitoring_checks["slo_targets_acceptable"],
            alert_routing_configured=monitoring_checks["alert_routing_configured"],
            governance_compliance_evidence_present=governance_checks["governance_compliance_evidence_present"],
            audit_chain_valid=governance_checks["audit_chain_valid"],
            no_unresolved_critical_policy_violation=governance_checks["no_unresolved_critical_policy_violation"],
            four_eyes_signoff_present=governance_checks["four_eyes_signoff_present"],
            compliance_checklist_passed=governance_checks["compliance_checklist_passed"],
            ha_dr_evidence_present=ha_dr_checks["ha_dr_evidence_present"],
            backup_verified=ha_dr_checks["backup_verified"],
            restore_tested=ha_dr_checks["restore_tested"],
            ha_audit_chain_valid=ha_dr_checks["ha_audit_chain_valid"],
            recovery_readiness_ready=ha_dr_checks["recovery_readiness_ready"],
            retention_compliant=ha_dr_checks["retention_compliant"],
            no_unresolved_dr_failure=ha_dr_checks["no_unresolved_dr_failure"],
            certification_package_present=certification_checks["certification_package_present"],
            evidence_quality_acceptable=certification_checks["evidence_quality_acceptable"],
            review_workflow_completed=certification_checks["review_workflow_completed"],
            no_critical_certification_failure=certification_checks["no_critical_certification_failure"],
            certification_governance_compliance_pass=certification_checks["certification_governance_compliance_pass"],
            certification_ha_dr_pass=certification_checks["certification_ha_dr_pass"],
        )
        failures = tuple(name for name, passed in checklist.__dict__.items() if name not in {"human_reviewer_signoff_required", "go_live_allowed"} and not passed)
        if not checklist.evidence_pack_exported or not checklist.operational_runbook_followed:
            decision = ManualReviewDecision.BLOCKED_FOR_REVIEW
        elif failures:
            decision = ManualReviewDecision.CONTINUE_SHADOW
        else:
            decision = ManualReviewDecision.READY_FOR_MANUAL_REVIEW
        return ManualReviewGateResult(decision, checklist, failures, False)

    @staticmethod
    def _scorecard_from_evidence(evidence_pack: EvidencePack | None) -> RobustnessScorecard | None:
        if evidence_pack is None:
            return None
        section = evidence_pack.sections.get("robustness_validation_json")
        if not isinstance(section, dict):
            return None
        raw = section.get("scorecard")
        if not isinstance(raw, dict):
            return None
        try:
            recommendation = RobustnessRecommendation(str(raw.get("recommendation")))
            return RobustnessScorecard(
                overall_score=float(raw.get("overall_score", 0.0)),
                data_quality_score=float(raw.get("data_quality_score", 0.0)),
                sample_size_score=float(raw.get("sample_size_score", 0.0)),
                regime_stability_score=float(raw.get("regime_stability_score", 0.0)),
                symbol_stability_score=float(raw.get("symbol_stability_score", 0.0)),
                timeframe_stability_score=float(raw.get("timeframe_stability_score", 0.0)),
                drawdown_quality_score=float(raw.get("drawdown_quality_score", 0.0)),
                execution_realism_score=float(raw.get("execution_realism_score", 0.0)),
                overfitting_risk_score=float(raw.get("overfitting_risk_score", 0.0)),
                recommendation=recommendation,
                failed_checks=tuple(raw.get("failed_checks", ())),
                warnings=tuple(raw.get("warnings", ())),
                critical_flags=tuple(raw.get("critical_flags", ())),
                go_live_allowed=False,
            )
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _multi_strategy_checks(evidence_pack: EvidencePack | None) -> dict[str, bool]:
        if evidence_pack is None:
            return {
                "strategy_diversification_acceptable": False,
                "strategy_correlation_acceptable": False,
                "strategy_health_acceptable": False,
                "no_disabled_strategy_dominating": False,
            }
        section = evidence_pack.sections.get("multi_strategy_json")
        if not isinstance(section, dict):
            return {
                "strategy_diversification_acceptable": False,
                "strategy_correlation_acceptable": False,
                "strategy_health_acceptable": False,
                "no_disabled_strategy_dominating": False,
            }
        allocations = section.get("allocations", {})
        allocation_map = allocations.get("allocations", {}) if isinstance(allocations, dict) else {}
        health_scores = section.get("health_scores", {})
        overlap_warnings = tuple(section.get("overlap_warnings", ()))
        active_allocations = [value for value in allocation_map.values() if isinstance(value, (int, float)) and value > 0]
        disabled_dominating = False
        for strategy_id, health in health_scores.items() if isinstance(health_scores, dict) else ():
            if isinstance(health, dict) and str(health.get("status")) == "DISABLED" and float(allocation_map.get(strategy_id, 0.0) or 0.0) > 0:
                disabled_dominating = True
        health_ok = bool(health_scores) and all(not (isinstance(health, dict) and str(health.get("status")) in {"DEGRADED", "DISABLED"} and float(allocation_map.get(strategy_id, 0.0) or 0.0) > 0) for strategy_id, health in health_scores.items())
        return {
            "strategy_diversification_acceptable": len(active_allocations) >= 2,
            "strategy_correlation_acceptable": not overlap_warnings,
            "strategy_health_acceptable": health_ok,
            "no_disabled_strategy_dominating": not disabled_dominating,
        }

    @staticmethod
    def _options_checks(evidence_pack: EvidencePack | None) -> dict[str, bool]:
        if evidence_pack is None:
            return {
                "options_greeks_acceptable": False,
                "options_concentration_acceptable": False,
                "options_expiry_risk_acceptable": False,
                "options_iv_exposure_acceptable": False,
            }
        section = evidence_pack.sections.get("options_risk_json")
        if not isinstance(section, dict):
            return {
                "options_greeks_acceptable": False,
                "options_concentration_acceptable": False,
                "options_expiry_risk_acceptable": False,
                "options_iv_exposure_acceptable": False,
            }
        warnings = tuple(section.get("risk_warnings", ()))
        greeks = section.get("greeks", {})
        iv = section.get("iv_metrics", {})
        expiry = section.get("expiry_metrics", {})
        concentration = section.get("concentration_metrics", {})
        greeks_status = getattr(greeks, "data_status", None) if not isinstance(greeks, dict) else greeks.get("data_status")
        iv_status = getattr(iv, "data_status", None) if not isinstance(iv, dict) else iv.get("data_status")
        expiry_status = getattr(expiry, "data_status", None) if not isinstance(expiry, dict) else expiry.get("data_status")
        approved = getattr(concentration, "approved", None) if not isinstance(concentration, dict) else concentration.get("approved")
        return {
            "options_greeks_acceptable": greeks_status == "OK" and not any("Greeks" in str(warning) or "delta" in str(warning) or "gamma" in str(warning) or "theta" in str(warning) or "vega" in str(warning) or "rho" in str(warning) for warning in warnings),
            "options_concentration_acceptable": approved is True and not any("concentration" in str(warning) or "lot" in str(warning) for warning in warnings),
            "options_expiry_risk_acceptable": expiry_status == "OK" and not any("expiry" in str(warning) for warning in warnings),
            "options_iv_exposure_acceptable": iv_status == "OK" and not any("IV" in str(warning) or "iv" in str(warning) for warning in warnings),
        }

    @staticmethod
    def _execution_checks(evidence_pack: EvidencePack | None) -> dict[str, bool]:
        if evidence_pack is None:
            return {
                "execution_realism_evidence_present": False,
                "execution_fill_ratio_acceptable": False,
                "execution_slippage_acceptable": False,
                "execution_market_impact_acceptable": False,
                "execution_latency_acceptable": False,
                "no_critical_impossible_fill_warnings": False,
            }
        section = evidence_pack.sections.get("execution_realism_json")
        if not isinstance(section, dict):
            return {
                "execution_realism_evidence_present": False,
                "execution_fill_ratio_acceptable": False,
                "execution_slippage_acceptable": False,
                "execution_market_impact_acceptable": False,
                "execution_latency_acceptable": False,
                "no_critical_impossible_fill_warnings": False,
            }
        warnings = tuple(str(warning) for warning in section.get("warnings", ()))
        impact = tuple(str(warning) for warning in section.get("impact_warnings", ()))
        reports = tuple(section.get("execution_reports", ()))
        latency_reports = tuple(section.get("latency_reports", ()))
        return {
            "execution_realism_evidence_present": bool(reports),
            "execution_fill_ratio_acceptable": float(section.get("fill_ratio", 0.0) or 0.0) >= 0.80,
            "execution_slippage_acceptable": not any("slippage" in warning.lower() for warning in warnings),
            "execution_market_impact_acceptable": not impact,
            "execution_latency_acceptable": not any((isinstance(report, dict) and report.get("latency_warning")) for report in latency_reports),
            "no_critical_impossible_fill_warnings": not any("impossible" in warning.lower() for warning in warnings + impact),
        }

    @staticmethod
    def _monitoring_checks(evidence_pack: EvidencePack | None) -> dict[str, bool]:
        if evidence_pack is None:
            return {
                "monitoring_evidence_present": False,
                "no_unresolved_critical_incidents": False,
                "slo_targets_acceptable": False,
                "alert_routing_configured": False,
            }
        section = evidence_pack.sections.get("monitoring_json")
        if not isinstance(section, dict):
            return {
                "monitoring_evidence_present": False,
                "no_unresolved_critical_incidents": False,
                "slo_targets_acceptable": False,
                "alert_routing_configured": False,
            }
        slo = section.get("slo_status", {})
        return {
            "monitoring_evidence_present": True,
            "no_unresolved_critical_incidents": not tuple(section.get("unresolved_critical_incidents", ())),
            "slo_targets_acceptable": bool(slo.get("targets_acceptable", False)) if isinstance(slo, dict) else False,
            "alert_routing_configured": bool(section.get("alert_routing_configured", False)),
        }

    @staticmethod
    def _governance_checks(evidence_pack: EvidencePack | None) -> dict[str, bool]:
        if evidence_pack is None:
            return {
                "governance_compliance_evidence_present": False,
                "audit_chain_valid": False,
                "no_unresolved_critical_policy_violation": False,
                "four_eyes_signoff_present": False,
                "compliance_checklist_passed": False,
            }
        section = evidence_pack.sections.get("governance_compliance_json")
        if not isinstance(section, dict):
            return {
                "governance_compliance_evidence_present": False,
                "audit_chain_valid": False,
                "no_unresolved_critical_policy_violation": False,
                "four_eyes_signoff_present": False,
                "compliance_checklist_passed": False,
            }
        chain = section.get("audit_chain_verification", {})
        checklist = section.get("compliance_checklist", {})
        approvals = tuple(section.get("four_eyes_approvals", ()))
        return {
            "governance_compliance_evidence_present": True,
            "audit_chain_valid": bool(chain.get("chain_valid", False)) if isinstance(chain, dict) else False,
            "no_unresolved_critical_policy_violation": not tuple(section.get("unresolved_governance_blocks", ())),
            "four_eyes_signoff_present": all(isinstance(approval, dict) and approval.get("approved") is True for approval in approvals) if approvals else True,
            "compliance_checklist_passed": bool(checklist.get("passed", False)) if isinstance(checklist, dict) else False,
        }


    @staticmethod
    def _ha_dr_checks(evidence_pack: EvidencePack | None) -> dict[str, bool]:
        if evidence_pack is None:
            return {
                "ha_dr_evidence_present": False,
                "backup_verified": False,
                "restore_tested": False,
                "ha_audit_chain_valid": False,
                "recovery_readiness_ready": False,
                "retention_compliant": False,
                "no_unresolved_dr_failure": False,
            }
        section = evidence_pack.sections.get("ha_disaster_recovery_json")
        if not isinstance(section, dict) or section.get("data_status") == "DATA_UNAVAILABLE":
            return {
                "ha_dr_evidence_present": False,
                "backup_verified": False,
                "restore_tested": False,
                "ha_audit_chain_valid": False,
                "recovery_readiness_ready": False,
                "retention_compliant": False,
                "no_unresolved_dr_failure": False,
            }
        backups = tuple(section.get("backup_reports", ()))
        restores = tuple(section.get("restore_reports", ()))
        readiness = section.get("recovery_readiness", {})
        retention = section.get("retention_compliance", {})
        dr_reports = tuple(section.get("dr_simulations", ()))
        ha_status = section.get("ha_status", {})
        backup_verified = bool(backups) and all(isinstance(report, dict) and report.get("verified") is True for report in backups)
        restore_tested = bool(restores) and all(isinstance(report, dict) and report.get("restore_success") is True for report in restores)
        recovery_ready = isinstance(readiness, dict) and readiness.get("recommendation") == "READY"
        retention_ok = isinstance(retention, dict) and retention.get("compliant") is True
        dr_ok = bool(dr_reports) and all(isinstance(report, dict) and report.get("recovery_success") is True for report in dr_reports)
        return {
            "ha_dr_evidence_present": True,
            "backup_verified": backup_verified,
            "restore_tested": restore_tested,
            "ha_audit_chain_valid": isinstance(readiness, dict) and readiness.get("audit_chain_valid") is True and (not isinstance(ha_status, dict) or ha_status.get("audit_chain_integrity", True) is True),
            "recovery_readiness_ready": recovery_ready,
            "retention_compliant": retention_ok,
            "no_unresolved_dr_failure": dr_ok,
        }


    @staticmethod
    def _certification_checks(evidence_pack: EvidencePack | None) -> dict[str, bool]:
        if evidence_pack is None:
            return {
                "certification_package_present": False,
                "evidence_quality_acceptable": False,
                "review_workflow_completed": False,
                "no_critical_certification_failure": False,
                "certification_governance_compliance_pass": False,
                "certification_ha_dr_pass": False,
            }
        section = evidence_pack.sections.get("final_certification_json")
        if not isinstance(section, dict) or section.get("data_status") == "DATA_UNAVAILABLE":
            return {
                "certification_package_present": False,
                "evidence_quality_acceptable": False,
                "review_workflow_completed": False,
                "no_critical_certification_failure": False,
                "certification_governance_compliance_pass": False,
                "certification_ha_dr_pass": False,
            }
        scorecard = section.get("certification_scorecard", {})
        readiness = section.get("readiness_report", {})
        evidence_quality = section.get("evidence_quality", {})
        workflow = section.get("review_workflow", {})
        package = section.get("certification_package_metadata", {})
        failed = tuple(scorecard.get("failed_sections", ())) if isinstance(scorecard, dict) else ()
        blockers = tuple(readiness.get("critical_blockers", ())) if isinstance(readiness, dict) else ()
        return {
            "certification_package_present": bool(package) and package.get("go_live_allowed") is False,
            "evidence_quality_acceptable": bool(evidence_quality.get("acceptable", False)) if isinstance(evidence_quality, dict) else False,
            "review_workflow_completed": bool(workflow.get("completed", False)) if isinstance(workflow, dict) else False,
            "no_critical_certification_failure": not failed and not blockers,
            "certification_governance_compliance_pass": "Governance" not in failed and "Compliance" not in failed and "governance_compliance_json" not in blockers,
            "certification_ha_dr_pass": "HA/DR" not in failed and "ha_disaster_recovery_json" not in blockers,
        }
