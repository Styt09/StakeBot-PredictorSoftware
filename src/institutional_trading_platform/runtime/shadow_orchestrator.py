"""Real shadow trading orchestrator for Phase 10.

The orchestrator coordinates read-only shadow operations and preview-only approval
flows. It never enables LIVE_AUTO and never places real broker orders.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from ..alpha_gate_x import TradingMode
from ..broker.approval_mode import ApprovalModeService
from ..broker.order_preview import ZerodhaOrderSafetyWrapper
from ..broker.reconciliation import BrokerReconciliationService
from ..broker.zerodha_auth import ZerodhaAuthService, ZerodhaConnectionStatus
from ..broker.zerodha_instrument_manager import ZerodhaInstrumentManager
from ..market_data_spine import Tick
from .config_hardening import ProductionRuntimeConfig
from .dashboard import DashboardSummaryService
from .daily_report import DailyShadowReport, DailyShadowReportGenerator
from .evidence_pack import EvidencePack, EvidencePackGenerator
from .event_bus import EventBus, RuntimeEvent, RuntimeEventType
from .live_paper_engine import LivePaperTradingEngine
from .manual_review import ManualReviewGate, ManualReviewGateResult
from .persistence import PersistenceUnavailable, SQLiteAuditStore
from .recovery import CrashRecoveryService, RecoveryMode
from .shadow_run import ShadowRunStatus, ShadowRunValidator


class ShadowOrchestratorState(StrEnum):
    BLOCKED = "BLOCKED"
    RUNNING = "RUNNING"
    SAFE_RECOVERY = "SAFE_RECOVERY"


@dataclass(frozen=True)
class ShadowOrchestratorStatus:
    state: ShadowOrchestratorState
    reasons: tuple[str, ...] = ()
    go_live_allowed: bool = False


@dataclass
class ShadowTradingOrchestrator:
    config: ProductionRuntimeConfig
    audit_store: SQLiteAuditStore
    event_bus: EventBus
    engine: LivePaperTradingEngine
    auth_service: ZerodhaAuthService
    instrument_manager: ZerodhaInstrumentManager
    reconciliation: BrokerReconciliationService
    recovery: CrashRecoveryService
    dashboard: DashboardSummaryService
    shadow: ShadowRunValidator
    status: ShadowOrchestratorStatus = field(default_factory=lambda: ShadowOrchestratorStatus(ShadowOrchestratorState.BLOCKED, ("not started",)))

    def start(self, *, reconciliation_passed: bool) -> ShadowOrchestratorStatus:
        reasons: list[str] = []
        if not self.config.valid:
            reasons.extend(self.config.failure_reasons)
        if self.config.trading_mode == TradingMode.LIVE_AUTO:
            reasons.append("LIVE_AUTO rejected")
        try:
            health = self.audit_store.health()
        except PersistenceUnavailable as exc:
            health = {"status": "failed", "error": str(exc)}
        if health.get("status") != "ok":
            reasons.append("persistence unavailable")
        recovery_status = self.recovery.recover(reconciliation_passed=reconciliation_passed)
        if recovery_status.mode == RecoveryMode.SAFE_RECOVERY:
            reasons.append("SAFE_RECOVERY active")
        auth = self.auth_service.validate()
        if auth.status != ZerodhaConnectionStatus.CONNECTED:
            reasons.append("Zerodha unavailable")
        if not self.reconciliation.last_result.passed:
            reasons.append("reconciliation has not passed")
        if reasons:
            self.status = ShadowOrchestratorStatus(ShadowOrchestratorState.SAFE_RECOVERY if "SAFE_RECOVERY active" in reasons else ShadowOrchestratorState.BLOCKED, tuple(reasons), False)
            return self.status
        self.status = ShadowOrchestratorStatus(ShadowOrchestratorState.RUNNING, (), False)
        return self.status

    def ingest_tick(self, tick: Tick) -> tuple[RuntimeEvent, ...]:
        if self.status.state != ShadowOrchestratorState.RUNNING:
            self.event_bus.publish(RuntimeEvent(RuntimeEventType.RISK_BLOCKED, tick.symbol, {"reasons": ("shadow orchestrator blocked",)}, severity="CRITICAL"))
            return ()
        return self.engine.on_tick(tick)

    def request_approval_for_latest_signal(self, signal: object) -> object:
        if not self.reconciliation.last_result.passed:
            raise RuntimeError("reconciliation must pass before approval request")
        wrapper = ZerodhaOrderSafetyWrapper(event_bus=self.event_bus, idempotency_store=self.audit_store)
        approval = ApprovalModeService(self.engine.config, self.reconciliation, wrapper, event_bus=self.event_bus)
        return approval.request_approval(signal)  # type: ignore[arg-type]

    def generate_daily_report(self, trading_day) -> DailyShadowReport:
        return DailyShadowReportGenerator(self.audit_store).generate(trading_day)

    def generate_evidence_pack(self, *, validation_report: object | None = None) -> EvidencePack:
        return EvidencePackGenerator(self.audit_store, self.dashboard, self.shadow).generate(config_summary=self.config.__dict__, validation_report=validation_report)

    def manual_review(self, evidence_pack: EvidencePack | None, *, runbook_followed: bool = False) -> ManualReviewGateResult:
        return ManualReviewGate().evaluate(self.shadow.status(), evidence_pack, runbook_followed=runbook_followed)

    def shadow_status(self) -> ShadowRunStatus:
        return self.shadow.status()
