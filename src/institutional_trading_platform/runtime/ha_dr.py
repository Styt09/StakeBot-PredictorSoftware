"""High availability, backup, restore, and disaster-recovery controls for Phase 19."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

from .governance import TamperEvidentAuditChain


class HAState(StrEnum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
    DISASTER_RECOVERY_MODE = "DISASTER_RECOVERY_MODE"


@dataclass(frozen=True)
class HAHealthStatus:
    runtime_status: str
    persistence_status: str
    database_availability: bool
    backup_availability: bool
    restore_readiness: bool
    recovery_readiness: bool
    audit_chain_integrity: bool
    reconciliation_readiness: bool
    shadow_run_continuity: bool
    state: HAState
    go_live_allowed: bool = False

    def to_dict(self) -> dict[str, object]:
        return {**asdict(self), "state": self.state.value, "go_live_allowed": False}

    @classmethod
    def evaluate(cls, *, runtime_status: str = "RUNNING", persistence_status: str = "AVAILABLE", database_availability: bool, backup_availability: bool, restore_readiness: bool, recovery_readiness: bool, audit_chain_integrity: bool, reconciliation_readiness: bool, shadow_run_continuity: bool) -> "HAHealthStatus":
        critical = not database_availability or not audit_chain_integrity
        recovery_needed = not restore_readiness or not recovery_readiness
        degraded = not backup_availability or not reconciliation_readiness or not shadow_run_continuity or persistence_status != "AVAILABLE" or runtime_status not in {"RUNNING", "PAPER", "SHADOW"}
        state = HAState.HEALTHY
        if critical:
            state = HAState.DISASTER_RECOVERY_MODE
        elif recovery_needed:
            state = HAState.RECOVERY_REQUIRED
        elif degraded:
            state = HAState.DEGRADED
        return cls(runtime_status, persistence_status, database_availability, backup_availability, restore_readiness, recovery_readiness, audit_chain_integrity, reconciliation_readiness, shadow_run_continuity, state, False)


class BackupType(StrEnum):
    FULL = "FULL"
    INCREMENTAL_METADATA = "INCREMENTAL_METADATA"
    AUDIT_EXPORT = "AUDIT_EXPORT"
    EVIDENCE_PACK = "EVIDENCE_PACK"
    SNAPSHOT = "SNAPSHOT"
    GOVERNANCE = "GOVERNANCE"


class BackupStatus(StrEnum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"


@dataclass(frozen=True)
class BackupMetadata:
    backup_id: str
    backup_type: BackupType
    timestamp: datetime
    path: str
    size: int
    checksum: str
    status: BackupStatus
    source_path: str | None = None
    warnings: tuple[str, ...] = ()
    go_live_allowed: bool = False

    def to_dict(self) -> dict[str, object]:
        return {**asdict(self), "backup_type": self.backup_type.value, "timestamp": self.timestamp.isoformat(), "status": self.status.value, "go_live_allowed": False}


@dataclass(frozen=True)
class BackupVerificationReport:
    verified: bool
    corrupted_files: tuple[str, ...]
    missing_files: tuple[str, ...]
    warnings: tuple[str, ...]
    go_live_allowed: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self) | {"go_live_allowed": False}


class BackupManager:
    def __init__(self, backup_root: str | Path) -> None:
        self.backup_root = Path(backup_root)
        self.backup_root.mkdir(parents=True, exist_ok=True)

    def create_backup(self, source_path: str | Path, backup_type: BackupType = BackupType.FULL, *, backup_id: str | None = None) -> BackupMetadata:
        source = Path(source_path)
        backup_id = backup_id or f"backup-{uuid4()}"
        target = self.backup_root / f"{backup_id}-{source.name}"
        now = datetime.now(timezone.utc)
        if not source.exists():
            return BackupMetadata(backup_id, backup_type, now, str(target), 0, "", BackupStatus.FAILED, str(source), ("source missing",), False)
        if source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True)
        else:
            shutil.copy2(source, target)
        checksum = self.generate_checksum(target)
        return BackupMetadata(backup_id, backup_type, now, str(target), self._size(target), checksum, BackupStatus.SUCCESS, str(source), (), False)

    def create_json_backup(self, payload: dict[str, object], backup_type: BackupType, *, backup_id: str | None = None) -> BackupMetadata:
        backup_id = backup_id or f"backup-{uuid4()}"
        target = self.backup_root / f"{backup_id}.json"
        target.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
        return BackupMetadata(backup_id, backup_type, datetime.now(timezone.utc), str(target), self._size(target), self.generate_checksum(target), BackupStatus.SUCCESS, None, (), False)

    def generate_checksum(self, path: str | Path) -> str:
        path = Path(path)
        digest = hashlib.sha256()
        if path.is_dir():
            for child in sorted(p for p in path.rglob("*") if p.is_file()):
                digest.update(str(child.relative_to(path)).encode())
                digest.update(child.read_bytes())
        else:
            digest.update(path.read_bytes())
        return digest.hexdigest()

    def verify_backup(self, metadata: BackupMetadata) -> BackupVerificationReport:
        path = Path(metadata.path)
        if not path.exists():
            return BackupVerificationReport(False, (), (metadata.path,), ("backup file missing",), False)
        checksum = self.generate_checksum(path)
        if checksum != metadata.checksum:
            return BackupVerificationReport(False, (metadata.path,), (), ("checksum mismatch",), False)
        return BackupVerificationReport(True, (), (), (), False)

    @staticmethod
    def _size(path: Path) -> int:
        if path.is_dir():
            return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())
        return path.stat().st_size


@dataclass(frozen=True)
class RestoreReport:
    restore_success: bool
    restored_objects: tuple[str, ...]
    warnings: tuple[str, ...]
    errors: tuple[str, ...]
    go_live_allowed: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self) | {"go_live_allowed": False}


class RestoreManager:
    def restore(self, metadata: BackupMetadata, restore_path: str | Path, verifier: BackupManager | None = None) -> RestoreReport:
        if verifier is not None and not verifier.verify_backup(metadata).verified:
            return RestoreReport(False, (), (), ("backup verification failed",), False)
        source = Path(metadata.path)
        target = Path(restore_path)
        if not source.exists():
            return RestoreReport(False, (), (), ("backup source missing",), False)
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True)
        else:
            shutil.copy2(source, target)
        return RestoreReport(True, (str(target),), (), (), False)


class DisasterScenario(StrEnum):
    PROCESS_CRASH = "PROCESS_CRASH"
    DATABASE_LOSS = "DATABASE_LOSS"
    SNAPSHOT_CORRUPTION = "SNAPSHOT_CORRUPTION"
    PERSISTENCE_FAILURE = "PERSISTENCE_FAILURE"
    RESTART_RECOVERY = "RESTART_RECOVERY"
    MISSING_BACKUP = "MISSING_BACKUP"
    STALE_BACKUP = "STALE_BACKUP"


@dataclass(frozen=True)
class DisasterRecoveryReport:
    scenario: DisasterScenario
    simulated_at: datetime
    recovery_success: bool
    recovery_required: bool
    warnings: tuple[str, ...]
    errors: tuple[str, ...]
    go_live_allowed: bool = False

    def to_dict(self) -> dict[str, object]:
        return {**asdict(self), "scenario": self.scenario.value, "simulated_at": self.simulated_at.isoformat(), "go_live_allowed": False}


class DisasterRecoverySimulator:
    def simulate(self, scenario: DisasterScenario, *, backup_available: bool = True, checksum_valid: bool = True, restore_tested: bool = True) -> DisasterRecoveryReport:
        errors: list[str] = []
        warnings: list[str] = []
        if scenario == DisasterScenario.MISSING_BACKUP or not backup_available:
            errors.append("backup unavailable")
        if scenario == DisasterScenario.SNAPSHOT_CORRUPTION or not checksum_valid:
            errors.append("checksum or snapshot corruption detected")
        if scenario == DisasterScenario.STALE_BACKUP:
            warnings.append("backup is stale")
        if not restore_tested:
            warnings.append("restore path not tested")
        return DisasterRecoveryReport(scenario, datetime.now(timezone.utc), not errors, bool(errors or warnings), tuple(warnings), tuple(errors), False)


class RecoveryReadinessRecommendation(StrEnum):
    READY = "READY"
    NOT_READY = "NOT_READY"


@dataclass(frozen=True)
class RecoveryReadinessReport:
    backup_exists: bool
    backup_recent_enough: bool
    checksum_valid: bool
    restore_tested: bool
    recovery_path_tested: bool
    audit_chain_valid: bool
    recommendation: RecoveryReadinessRecommendation
    failure_reasons: tuple[str, ...]
    go_live_allowed: bool = False

    def to_dict(self) -> dict[str, object]:
        return {**asdict(self), "recommendation": self.recommendation.value, "go_live_allowed": False}


class RecoveryReadinessValidator:
    def validate(self, *, backup_metadata: BackupMetadata | None, verification_report: BackupVerificationReport | None, restore_report: RestoreReport | None, recovery_reports: tuple[DisasterRecoveryReport, ...], audit_chain: TamperEvidentAuditChain | None = None, max_backup_age: timedelta = timedelta(days=1)) -> RecoveryReadinessReport:
        now = datetime.now(timezone.utc)
        backup_exists = backup_metadata is not None and backup_metadata.status == BackupStatus.SUCCESS and Path(backup_metadata.path).exists()
        recent = bool(backup_metadata and now - backup_metadata.timestamp <= max_backup_age)
        checksum_valid = bool(verification_report and verification_report.verified)
        restore_tested = bool(restore_report and restore_report.restore_success)
        recovery_path_tested = bool(recovery_reports) and all(report.recovery_success for report in recovery_reports)
        audit_chain_valid = audit_chain.verify_full_chain().chain_valid if audit_chain is not None else False
        checks = {"backup_exists": backup_exists, "backup_recent_enough": recent, "checksum_valid": checksum_valid, "restore_tested": restore_tested, "recovery_path_tested": recovery_path_tested, "audit_chain_valid": audit_chain_valid}
        failures = tuple(name for name, ok in checks.items() if not ok)
        recommendation = RecoveryReadinessRecommendation.READY if not failures else RecoveryReadinessRecommendation.NOT_READY
        return RecoveryReadinessReport(backup_exists, recent, checksum_valid, restore_tested, recovery_path_tested, audit_chain_valid, recommendation, failures, False)


@dataclass(frozen=True)
class RetentionPolicy:
    daily_backups: int = 7
    weekly_backups: int = 4
    monthly_backups: int = 12


@dataclass(frozen=True)
class RetentionComplianceReport:
    compliant: bool
    expired_backups: tuple[str, ...]
    warnings: tuple[str, ...]
    go_live_allowed: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self) | {"go_live_allowed": False}


class BackupRetentionManager:
    def __init__(self, policy: RetentionPolicy = RetentionPolicy()) -> None:
        self.policy = policy

    def evaluate(self, backups: tuple[BackupMetadata, ...], *, now: datetime | None = None) -> RetentionComplianceReport:
        now = now or datetime.now(timezone.utc)
        if not backups:
            return RetentionComplianceReport(False, (), ("no backups available",), False)
        max_age = timedelta(days=max(self.policy.daily_backups, self.policy.weekly_backups * 7, self.policy.monthly_backups * 31))
        expired = tuple(backup.backup_id for backup in backups if now - backup.timestamp > max_age)
        latest_age = min(now - backup.timestamp for backup in backups)
        warnings = []
        if latest_age > timedelta(days=1):
            warnings.append("latest daily backup is older than 1 day")
        if expired:
            warnings.append("one or more backups exceed retention window")
        return RetentionComplianceReport(not warnings, expired, tuple(warnings), False)


class BusinessContinuityRecommendation(StrEnum):
    CONTINUE_SHADOW = "CONTINUE_SHADOW"
    RECOVERY_IMPROVEMENT_REQUIRED = "RECOVERY_IMPROVEMENT_REQUIRED"
    READY_FOR_MANUAL_REVIEW = "READY_FOR_MANUAL_REVIEW"


@dataclass(frozen=True)
class BusinessContinuityReport:
    backup_status: str
    restore_status: str
    recovery_readiness: str
    recovery_test_history: tuple[dict[str, object], ...]
    retention_compliance: bool
    disaster_recovery_score: float
    recommendation: BusinessContinuityRecommendation
    warnings: tuple[str, ...]
    go_live_allowed: bool = False

    def to_dict(self) -> dict[str, object]:
        return {**asdict(self), "recommendation": self.recommendation.value, "go_live_allowed": False}


class BusinessContinuityReporter:
    def build(self, *, backup_report: BackupVerificationReport | None, restore_report: RestoreReport | None, readiness_report: RecoveryReadinessReport | None, retention_report: RetentionComplianceReport | None, dr_reports: tuple[DisasterRecoveryReport, ...]) -> BusinessContinuityReport:
        backup_ok = bool(backup_report and backup_report.verified)
        restore_ok = bool(restore_report and restore_report.restore_success)
        readiness_ok = bool(readiness_report and readiness_report.recommendation == RecoveryReadinessRecommendation.READY)
        retention_ok = bool(retention_report and retention_report.compliant)
        dr_ok = bool(dr_reports) and all(report.recovery_success for report in dr_reports)
        score = 100.0 * sum((backup_ok, restore_ok, readiness_ok, retention_ok, dr_ok)) / 5.0
        warnings = tuple(reason for ok, reason in ((backup_ok, "backup not verified"), (restore_ok, "restore not tested"), (readiness_ok, "recovery readiness not ready"), (retention_ok, "retention policy not compliant"), (dr_ok, "DR simulation failed or missing")) if not ok)
        recommendation = BusinessContinuityRecommendation.READY_FOR_MANUAL_REVIEW if score == 100.0 else (BusinessContinuityRecommendation.RECOVERY_IMPROVEMENT_REQUIRED if score < 80.0 else BusinessContinuityRecommendation.CONTINUE_SHADOW)
        return BusinessContinuityReport("VERIFIED" if backup_ok else "UNVERIFIED", "TESTED" if restore_ok else "UNTESTED", readiness_report.recommendation.value if readiness_report else "NOT_READY", tuple(report.to_dict() for report in dr_reports), retention_ok, score, recommendation, warnings, False)


def ha_disaster_recovery_evidence_section(*, ha_status: HAHealthStatus | None = None, backup_reports: tuple[BackupVerificationReport, ...] = (), restore_reports: tuple[RestoreReport, ...] = (), recovery_readiness: RecoveryReadinessReport | None = None, retention_compliance: RetentionComplianceReport | None = None, dr_simulations: tuple[DisasterRecoveryReport, ...] = (), business_continuity_report: BusinessContinuityReport | None = None) -> dict[str, object]:
    if ha_status is None and not backup_reports and not restore_reports and recovery_readiness is None and retention_compliance is None and not dr_simulations and business_continuity_report is None:
        return {"data_status": "DATA_UNAVAILABLE", "go_live_allowed": False}
    return {
        "ha_status": ha_status.to_dict() if ha_status else {"data_status": "DATA_UNAVAILABLE", "go_live_allowed": False},
        "backup_reports": tuple(report.to_dict() for report in backup_reports),
        "restore_reports": tuple(report.to_dict() for report in restore_reports),
        "recovery_readiness": recovery_readiness.to_dict() if recovery_readiness else {"data_status": "DATA_UNAVAILABLE", "go_live_allowed": False},
        "retention_compliance": retention_compliance.to_dict() if retention_compliance else {"data_status": "DATA_UNAVAILABLE", "go_live_allowed": False},
        "dr_simulations": tuple(report.to_dict() for report in dr_simulations),
        "business_continuity_report": business_continuity_report.to_dict() if business_continuity_report else {"data_status": "DATA_UNAVAILABLE", "go_live_allowed": False},
        "go_live_allowed": False,
    }
