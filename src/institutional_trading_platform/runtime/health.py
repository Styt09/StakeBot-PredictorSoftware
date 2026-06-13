"""Read-only health checks for Phase 9 production hardening."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .config_hardening import ProductionRuntimeConfig
from .dashboard import DashboardSummaryService
from .persistence import SQLiteAuditStore
from .recovery import CrashRecoveryService, RecoveryMode
from .shadow_run import ShadowRunValidator


@dataclass(frozen=True)
class HealthCheckResult:
    name: str
    ok: bool
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReadinessReport:
    ok: bool
    checks: tuple[HealthCheckResult, ...]
    go_live_allowed: bool = False


class HealthCheckService:
    """Aggregate liveness/readiness checks without side effects."""

    def __init__(self, config: ProductionRuntimeConfig, persistence: SQLiteAuditStore, dashboard: DashboardSummaryService, shadow: ShadowRunValidator, recovery: CrashRecoveryService | None = None) -> None:
        self.config = config
        self.persistence = persistence
        self.dashboard = dashboard
        self.shadow = shadow
        self.recovery = recovery

    def liveness(self) -> HealthCheckResult:
        return HealthCheckResult("liveness", True)

    def persistence_health(self) -> HealthCheckResult:
        health = self.persistence.health()
        return HealthCheckResult("persistence", health.get("status") == "ok", (str(health.get("error")),) if health.get("status") != "ok" else ())

    def readiness(self, now: datetime | None = None, *, in_market_session: bool = False) -> ReadinessReport:
        now = now or datetime.now(timezone.utc)
        summary = self.dashboard.summary(now=now)
        checks = [self.liveness(), self.persistence_health()]
        checks.append(HealthCheckResult("config", self.config.valid, self.config.failure_reasons))
        safe_recovery = self.recovery is not None and self.recovery.last_status.mode == RecoveryMode.SAFE_RECOVERY
        checks.append(HealthCheckResult("recovery", not safe_recovery, ("SAFE_RECOVERY active",) if safe_recovery else ()))
        recon_ok = summary.reconciliation_status in {"PASSED", "UNKNOWN"}
        checks.append(HealthCheckResult("reconciliation", recon_ok, ("reconciliation stale/failing",) if not recon_ok else ()))
        feed_ok = not (in_market_session and summary.stale_feed)
        checks.append(HealthCheckResult("market_feed", feed_ok, ("market feed stale during session",) if not feed_ok else ()))
        shadow = self.shadow.status()
        checks.append(HealthCheckResult("shadow_run", shadow.go_live_allowed is False, ()))
        return ReadinessReport(all(check.ok for check in checks), tuple(checks), False)

    def zerodha_auth_health(self) -> HealthCheckResult:
        summary = self.dashboard.summary()
        return HealthCheckResult("zerodha_auth", summary.zerodha_auth_status != "AUTH_FAILED", ("auth failed",) if summary.zerodha_auth_status == "AUTH_FAILED" else ())

    def websocket_freshness(self, now: datetime | None = None) -> HealthCheckResult:
        summary = self.dashboard.summary(now=now)
        return HealthCheckResult("websocket_freshness", not summary.stale_feed, ("stale feed",) if summary.stale_feed else ())

    def shadow_gate_health(self) -> HealthCheckResult:
        status = self.shadow.status()
        return HealthCheckResult("shadow_gate", status.go_live_allowed is False, status.failure_reasons)
