"""Governance, compliance, and tamper-evident audit controls for Phase 18."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4


class GovernanceAction(StrEnum):
    CONFIG_CHANGE_REQUESTED = "config_change_requested"
    CONFIG_CHANGE_APPROVED = "config_change_approved"
    CONFIG_CHANGE_REJECTED = "config_change_rejected"
    STRATEGY_ENABLED = "strategy_enabled"
    STRATEGY_DISABLED = "strategy_disabled"
    RISK_LIMIT_CHANGED = "risk_limit_changed"
    MANUAL_REVIEW_STARTED = "manual_review_started"
    MANUAL_REVIEW_COMPLETED = "manual_review_completed"
    EVIDENCE_PACK_EXPORTED = "evidence_pack_exported"
    INCIDENT_ACKNOWLEDGED = "incident_acknowledged"
    INCIDENT_RESOLVED = "incident_resolved"
    UNSAFE_ACTION_BLOCKED = "unsafe_action_blocked"
    APPROVAL_DECISION_RECORDED = "approval_decision_recorded"
    GOVERNANCE_POLICY_VIOLATION = "governance_policy_violation"


class ApprovalStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    BLOCKED = "BLOCKED"


class GovernanceSeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class GovernanceRole(StrEnum):
    VIEWER = "VIEWER"
    OPERATOR = "OPERATOR"
    RISK_MANAGER = "RISK_MANAGER"
    REVIEWER = "REVIEWER"
    ADMIN = "ADMIN"


class GovernancePermission(StrEnum):
    VIEW_REPORTS = "view_reports"
    ACKNOWLEDGE_INCIDENTS = "acknowledge_incidents"
    RESOLVE_INCIDENTS = "resolve_incidents"
    APPROVE_CONFIG_CHANGES = "approve_config_changes"
    APPROVE_MANUAL_REVIEW = "approve_manual_review"
    EXPORT_EVIDENCE = "export_evidence"
    DISABLE_STRATEGY = "disable_strategy"
    CHANGE_RISK_LIMIT = "change_risk_limit"


@dataclass(frozen=True)
class GovernanceEvent:
    governance_event_id: str
    timestamp: datetime
    actor: str
    actor_role: GovernanceRole
    action: GovernanceAction
    affected_resource: str
    reason: str
    correlation_id: str | None = None
    previous_value: object | None = None
    new_value: object | None = None
    approval_status: ApprovalStatus = ApprovalStatus.PENDING
    severity: GovernanceSeverity = GovernanceSeverity.INFO
    payload_json: dict[str, object] = field(default_factory=dict)

    @classmethod
    def create(cls, *, actor: str, actor_role: GovernanceRole, action: GovernanceAction, affected_resource: str, reason: str, correlation_id: str | None = None, previous_value: object | None = None, new_value: object | None = None, approval_status: ApprovalStatus = ApprovalStatus.PENDING, severity: GovernanceSeverity = GovernanceSeverity.INFO, payload_json: dict[str, object] | None = None, timestamp: datetime | None = None) -> "GovernanceEvent":
        return cls(
            governance_event_id=f"gov-{uuid4()}",
            timestamp=timestamp or datetime.now(timezone.utc),
            actor=actor,
            actor_role=actor_role,
            action=action,
            affected_resource=affected_resource,
            reason=reason,
            correlation_id=correlation_id,
            previous_value=previous_value,
            new_value=new_value,
            approval_status=approval_status,
            severity=severity,
            payload_json=payload_json or {},
        )

    def canonical_payload(self) -> dict[str, object]:
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        data["actor_role"] = self.actor_role.value
        data["action"] = self.action.value
        data["approval_status"] = self.approval_status.value
        data["severity"] = self.severity.value
        return data


@dataclass(frozen=True)
class ChainedGovernanceEvent:
    event: GovernanceEvent
    previous_hash: str
    event_hash: str
    chain_index: int
    chain_valid: bool = True

    def to_dict(self) -> dict[str, object]:
        return {"event": self.event.canonical_payload(), "previous_hash": self.previous_hash, "event_hash": self.event_hash, "chain_index": self.chain_index, "chain_valid": self.chain_valid}


@dataclass(frozen=True)
class AuditChainVerification:
    chain_valid: bool
    checked_events: int
    failures: tuple[str, ...]
    go_live_allowed: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class TamperEvidentAuditChain:
    """Hash-chained governance log. Tamper-evident, not tamper-proof."""

    GENESIS_HASH = "0" * 64

    def __init__(self) -> None:
        self._events: list[ChainedGovernanceEvent] = []

    def append(self, event: GovernanceEvent) -> ChainedGovernanceEvent:
        previous_hash = self._events[-1].event_hash if self._events else self.GENESIS_HASH
        chain_index = len(self._events)
        event_hash = self._hash(event, previous_hash, chain_index)
        chained = ChainedGovernanceEvent(event, previous_hash, event_hash, chain_index, True)
        self._events.append(chained)
        return chained

    def all(self) -> tuple[ChainedGovernanceEvent, ...]:
        return tuple(self._events)

    def verify_full_chain(self) -> AuditChainVerification:
        return self.verify_range(0, len(self._events))

    def verify_range(self, start_index: int, end_index: int) -> AuditChainVerification:
        failures: list[str] = []
        previous_hash = self.GENESIS_HASH if start_index == 0 else (self._events[start_index - 1].event_hash if start_index <= len(self._events) else self.GENESIS_HASH)
        for expected_index in range(start_index, min(end_index, len(self._events))):
            chained = self._events[expected_index]
            if chained.chain_index != expected_index:
                failures.append(f"chain index mismatch at {expected_index}")
            if chained.previous_hash != previous_hash:
                failures.append(f"previous hash mismatch at {expected_index}")
            expected_hash = self._hash(chained.event, chained.previous_hash, chained.chain_index)
            if chained.event_hash != expected_hash:
                failures.append(f"event hash mismatch at {expected_index}")
            previous_hash = chained.event_hash
        if end_index > len(self._events):
            failures.append("range extends beyond chain")
        return AuditChainVerification(not failures, max(0, min(end_index, len(self._events)) - start_index), tuple(failures), False)

    def detect_missing_or_modified_event(self) -> tuple[str, ...]:
        return self.verify_full_chain().failures

    @staticmethod
    def _hash(event: GovernanceEvent, previous_hash: str, chain_index: int) -> str:
        payload = {"event": event.canonical_payload(), "previous_hash": previous_hash, "chain_index": chain_index}
        raw = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()


ROLE_PERMISSIONS: dict[GovernanceRole, frozenset[GovernancePermission]] = {
    GovernanceRole.VIEWER: frozenset({GovernancePermission.VIEW_REPORTS}),
    GovernanceRole.OPERATOR: frozenset({GovernancePermission.VIEW_REPORTS, GovernancePermission.ACKNOWLEDGE_INCIDENTS, GovernancePermission.EXPORT_EVIDENCE}),
    GovernanceRole.RISK_MANAGER: frozenset({GovernancePermission.VIEW_REPORTS, GovernancePermission.ACKNOWLEDGE_INCIDENTS, GovernancePermission.RESOLVE_INCIDENTS, GovernancePermission.CHANGE_RISK_LIMIT, GovernancePermission.EXPORT_EVIDENCE}),
    GovernanceRole.REVIEWER: frozenset({GovernancePermission.VIEW_REPORTS, GovernancePermission.APPROVE_MANUAL_REVIEW, GovernancePermission.EXPORT_EVIDENCE}),
    GovernanceRole.ADMIN: frozenset(set(GovernancePermission) - set()),
}


class RoleBasedAccessControl:
    def permissions_for(self, role: GovernanceRole) -> frozenset[GovernancePermission]:
        return ROLE_PERMISSIONS[role]

    def has_permission(self, role: GovernanceRole, permission: GovernancePermission) -> bool:
        return permission in ROLE_PERMISSIONS[role]

    def can_enable_live_auto(self, role: GovernanceRole) -> bool:
        return False

    def summary(self) -> dict[str, object]:
        return {role.value: tuple(permission.value for permission in permissions) for role, permissions in ROLE_PERMISSIONS.items()} | {"live_auto_permission": False, "go_live_allowed": False}


@dataclass(frozen=True)
class FourEyesApproval:
    resource: str
    requested_by: str
    approved_by: str | None
    action: GovernanceAction
    approved: bool
    reason: str
    go_live_allowed: bool = False

    def to_dict(self) -> dict[str, object]:
        return {**asdict(self), "action": self.action.value, "go_live_allowed": False}


class FourEyesControl:
    REQUIRED_ACTIONS = {GovernanceAction.RISK_LIMIT_CHANGED, GovernanceAction.STRATEGY_ENABLED, GovernanceAction.STRATEGY_DISABLED, GovernanceAction.MANUAL_REVIEW_COMPLETED}

    def request_approval(self, *, resource: str, requested_by: str, approved_by: str | None, action: GovernanceAction) -> FourEyesApproval:
        if action in self.REQUIRED_ACTIONS and requested_by == approved_by:
            return FourEyesApproval(resource, requested_by, approved_by, action, False, "same actor cannot request and approve four-eyes action", False)
        if action in self.REQUIRED_ACTIONS and not approved_by:
            return FourEyesApproval(resource, requested_by, approved_by, action, False, "second actor approval required", False)
        return FourEyesApproval(resource, requested_by, approved_by, action, True, "four-eyes control satisfied", False)


class PolicyName(StrEnum):
    LIVE_AUTO_FORBIDDEN = "LIVE_AUTO_FORBIDDEN"
    REAL_ORDER_FORBIDDEN_BY_DEFAULT = "REAL_ORDER_FORBIDDEN_BY_DEFAULT"
    GO_LIVE_FALSE_REQUIRED = "GO_LIVE_FALSE_REQUIRED"
    EVIDENCE_REQUIRED_FOR_REVIEW = "EVIDENCE_REQUIRED_FOR_REVIEW"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    MONITORING_REQUIRED = "MONITORING_REQUIRED"
    EXECUTION_REALISM_REQUIRED = "EXECUTION_REALISM_REQUIRED"
    ROBUSTNESS_REQUIRED = "ROBUSTNESS_REQUIRED"
    OPTIONS_RISK_REQUIRED_IF_FNO_ENABLED = "OPTIONS_RISK_REQUIRED_IF_FNO_ENABLED"


@dataclass(frozen=True)
class PolicyViolation:
    policy: PolicyName
    severity: GovernanceSeverity
    message: str
    correlation_id: str | None = None
    resolved: bool = False
    go_live_allowed: bool = False

    def to_event(self, *, actor: str = "policy_engine") -> GovernanceEvent:
        return GovernanceEvent.create(actor=actor, actor_role=GovernanceRole.ADMIN, action=GovernanceAction.GOVERNANCE_POLICY_VIOLATION, affected_resource=self.policy.value, reason=self.message, correlation_id=self.correlation_id, approval_status=ApprovalStatus.BLOCKED, severity=self.severity, payload_json=self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {"policy": self.policy.value, "severity": self.severity.value, "message": self.message, "correlation_id": self.correlation_id, "resolved": self.resolved, "go_live_allowed": False}


class PolicyEngine:
    def evaluate(self, context: dict[str, object]) -> tuple[PolicyViolation, ...]:
        violations: list[PolicyViolation] = []
        if context.get("trading_mode") == "LIVE_AUTO" or context.get("live_auto_requested") is True:
            violations.append(PolicyViolation(PolicyName.LIVE_AUTO_FORBIDDEN, GovernanceSeverity.CRITICAL, "LIVE_AUTO is forbidden in this framework"))
        if context.get("real_order_enabled") is True:
            violations.append(PolicyViolation(PolicyName.REAL_ORDER_FORBIDDEN_BY_DEFAULT, GovernanceSeverity.CRITICAL, "real order placement is forbidden by default"))
        if context.get("go_live_allowed") is not False:
            violations.append(PolicyViolation(PolicyName.GO_LIVE_FALSE_REQUIRED, GovernanceSeverity.CRITICAL, "go_live_allowed must remain false"))
        required = (
            (PolicyName.EVIDENCE_REQUIRED_FOR_REVIEW, "evidence_pack_exported"),
            (PolicyName.RECONCILIATION_REQUIRED, "reconciliation_clean"),
            (PolicyName.MONITORING_REQUIRED, "monitoring_present"),
            (PolicyName.EXECUTION_REALISM_REQUIRED, "execution_realism_present"),
            (PolicyName.ROBUSTNESS_REQUIRED, "robustness_present"),
        )
        for policy, key in required:
            if context.get(key) is False:
                violations.append(PolicyViolation(policy, GovernanceSeverity.WARNING, f"{key} is required for review"))
        if context.get("fno_enabled") is True and context.get("options_risk_present") is not True:
            violations.append(PolicyViolation(PolicyName.OPTIONS_RISK_REQUIRED_IF_FNO_ENABLED, GovernanceSeverity.WARNING, "options risk evidence is required when F&O is enabled"))
        return tuple(violations)


class ComplianceRecommendation(StrEnum):
    CONTINUE_SHADOW = "CONTINUE_SHADOW"
    BLOCKED_FOR_COMPLIANCE_REVIEW = "BLOCKED_FOR_COMPLIANCE_REVIEW"
    READY_FOR_MANUAL_REVIEW = "READY_FOR_MANUAL_REVIEW"


@dataclass(frozen=True)
class ComplianceChecklistReport:
    audit_chain_verified: bool
    evidence_pack_exported: bool
    risk_limits_reviewed: bool
    manual_review_completed: bool
    incidents_resolved: bool
    monitoring_slo_met: bool
    reconciliation_clean: bool
    strategy_robustness_present: bool
    execution_realism_present: bool
    options_risk_present_if_fno_enabled: bool
    no_unsafe_broker_action: bool
    no_live_auto: bool
    recommendation: ComplianceRecommendation
    failure_reasons: tuple[str, ...]
    go_live_allowed: bool = False

    @property
    def passed(self) -> bool:
        return not self.failure_reasons

    def to_dict(self) -> dict[str, object]:
        return {**asdict(self), "recommendation": self.recommendation.value, "passed": self.passed, "go_live_allowed": False}


class ComplianceEngine:
    def build_report(self, *, audit_chain_verified: bool, evidence_pack_exported: bool, risk_limits_reviewed: bool, manual_review_completed: bool, incidents_resolved: bool, monitoring_slo_met: bool, reconciliation_clean: bool, strategy_robustness_present: bool, execution_realism_present: bool, options_risk_present_if_fno_enabled: bool, no_unsafe_broker_action: bool, no_live_auto: bool) -> ComplianceChecklistReport:
        checks = {
            "audit_chain_verified": audit_chain_verified,
            "evidence_pack_exported": evidence_pack_exported,
            "risk_limits_reviewed": risk_limits_reviewed,
            "manual_review_completed": manual_review_completed,
            "incidents_resolved": incidents_resolved,
            "monitoring_slo_met": monitoring_slo_met,
            "reconciliation_clean": reconciliation_clean,
            "strategy_robustness_present": strategy_robustness_present,
            "execution_realism_present": execution_realism_present,
            "options_risk_present_if_fno_enabled": options_risk_present_if_fno_enabled,
            "no_unsafe_broker_action": no_unsafe_broker_action,
            "no_live_auto": no_live_auto,
        }
        failures = tuple(name for name, ok in checks.items() if not ok)
        recommendation = ComplianceRecommendation.READY_FOR_MANUAL_REVIEW if not failures else (ComplianceRecommendation.BLOCKED_FOR_COMPLIANCE_REVIEW if not audit_chain_verified or not no_live_auto or not no_unsafe_broker_action else ComplianceRecommendation.CONTINUE_SHADOW)
        return ComplianceChecklistReport(**checks, recommendation=recommendation, failure_reasons=failures, go_live_allowed=False)


def governance_compliance_evidence_section(*, audit_chain: TamperEvidentAuditChain | None = None, rbac: RoleBasedAccessControl | None = None, policy_violations: tuple[PolicyViolation, ...] = (), compliance_report: ComplianceChecklistReport | None = None, four_eyes_approvals: tuple[FourEyesApproval, ...] = ()) -> dict[str, object]:
    chain = audit_chain or TamperEvidentAuditChain()
    verification = chain.verify_full_chain()
    rbac = rbac or RoleBasedAccessControl()
    report = compliance_report or ComplianceEngine().build_report(
        audit_chain_verified=verification.chain_valid,
        evidence_pack_exported=True,
        risk_limits_reviewed=True,
        manual_review_completed=True,
        incidents_resolved=True,
        monitoring_slo_met=True,
        reconciliation_clean=True,
        strategy_robustness_present=True,
        execution_realism_present=True,
        options_risk_present_if_fno_enabled=True,
        no_unsafe_broker_action=True,
        no_live_auto=True,
    )
    unresolved = tuple(v.to_dict() for v in policy_violations if v.severity == GovernanceSeverity.CRITICAL and not v.resolved)
    return {
        "governance_events": tuple(chained.to_dict() for chained in chain.all()),
        "audit_chain_verification": verification.to_dict(),
        "role_permission_summary": rbac.summary(),
        "policy_violations": tuple(violation.to_dict() for violation in policy_violations),
        "compliance_checklist": report.to_dict(),
        "four_eyes_approvals": tuple(approval.to_dict() for approval in four_eyes_approvals),
        "unresolved_governance_blocks": unresolved,
        "go_live_allowed": False,
    }
