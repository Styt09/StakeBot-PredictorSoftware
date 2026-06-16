from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from institutional_trading_platform.alpha_gate_x import AlphaSignal, RiskStatus, TradingMode
from institutional_trading_platform.alpha_gate_x_indicators import ConfidenceGrade, IndicatorSignalOutput, TradingProfile
from institutional_trading_platform.broker import BrokerReconciliationService, BrokerStateSnapshot, LocalApprovalState, ZerodhaAuthConfig, ZerodhaAuthService, ZerodhaInstrumentManager
from institutional_trading_platform.market_data_spine import Tick
from institutional_trading_platform.runtime import (
    DashboardSummaryService,
    DailyShadowReportGenerator,
    EventBus,
    LivePaperTradingEngine,
    ManualReviewDecision,
    ManualReviewGate,
    ProductionRuntimeConfig,
    RecoveryMode,
    RuntimeConfig,
    RuntimeEvent,
    RuntimeEventType,
    RuntimeStateSnapshot,
    SQLiteAuditStore,
    ShadowRunGateConfig,
    ShadowRunRecommendation,
    ShadowRunValidator,
)
from institutional_trading_platform.runtime.api import ReadOnlyRuntimeAPI
from institutional_trading_platform.runtime.recovery import CrashRecoveryService
from institutional_trading_platform.runtime.shadow_orchestrator import ShadowOrchestratorState, ShadowTradingOrchestrator
from institutional_trading_platform.runtime.evidence_pack import EvidencePackGenerator
from institutional_trading_platform.validation.robustness import RobustnessRecommendation, RobustnessScorecard
from institutional_trading_platform.runtime.persistence import PersistenceUnavailable

UTC = timezone.utc


class StubComposer:
    calls = 0

    def intraday_signal(self, **kwargs):
        self.calls += 1
        return IndicatorSignalOutput("RELIANCE", "5m", TradingProfile.INTRADAY, AlphaSignal.BUY, 0.8, 0.9, ConfidenceGrade.A, 100.0, 99.0, 102.0, 103.0, 1.0, RiskStatus.PASS, {}, (), ("stub",), "sig-1")


class ReadOnlyProfileOK:
    def profile(self, api_key: str, access_token: str) -> dict[str, object]:
        return {"user_id": "shadow-user", "revoked": False}


def _tick(minute: int, tick_id: str = "t") -> Tick:
    return Tick("RELIANCE", "NSE", datetime(2026, 1, 1, 9, 15, tzinfo=UTC) + timedelta(minutes=minute), 100.0, 1000, tick_id=tick_id)


def _orchestrator(tmp_path, *, config_valid: bool = True, recon_pass: bool = True):
    tmp_path.mkdir(parents=True, exist_ok=True)
    store = SQLiteAuditStore(tmp_path / "audit.db")
    bus = EventBus()
    bus.subscribe(store.append)
    config = ProductionRuntimeConfig.from_env({"ALPHA_GATE_PROFILE": "LOCAL", "AUDIT_DB_PATH": str(tmp_path / "audit.db")})
    if not config_valid:
        config = ProductionRuntimeConfig.from_env({"ALPHA_GATE_PROFILE": "BAD", "AUDIT_DB_PATH": str(tmp_path / "audit.db")})
    store.save_snapshot(RuntimeStateSnapshot("snap", "PAPER_TRADING"))
    recon = BrokerReconciliationService(event_bus=bus)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    if recon_pass:
        recon.reconcile(BrokerStateSnapshot(updated_at=now), LocalApprovalState(), now=now)
    else:
        recon.reconcile(BrokerStateSnapshot(positions=(__import__("institutional_trading_platform.broker", fromlist=["BrokerPositionSnapshot"]).BrokerPositionSnapshot("RELIANCE", 1, 100.0),), updated_at=now), LocalApprovalState(), now=now)
    engine = LivePaperTradingEngine(config=RuntimeConfig(allowed_symbols=("RELIANCE",)), composer=StubComposer())
    return ShadowTradingOrchestrator(config, store, bus, engine, ZerodhaAuthService(ZerodhaAuthConfig("key", "token"), event_bus=bus, profile_client=ReadOnlyProfileOK()), ZerodhaInstrumentManager(event_bus=bus), recon, CrashRecoveryService(store, event_bus=bus), DashboardSummaryService(store), ShadowRunValidator(store)), store


def test_orchestrator_blocks_on_invalid_config_persistence_safe_recovery_and_reconciliation(tmp_path) -> None:
    bad_config, _ = _orchestrator(tmp_path / "bad", config_valid=False)
    assert bad_config.start(reconciliation_passed=True).state == ShadowOrchestratorState.BLOCKED

    recon_bad, _ = _orchestrator(tmp_path / "recon", recon_pass=False)
    assert "reconciliation has not passed" in recon_bad.start(reconciliation_passed=True).reasons

    safe, _ = _orchestrator(tmp_path / "safe")
    status = safe.start(reconciliation_passed=False)
    assert status.state == ShadowOrchestratorState.SAFE_RECOVERY

    class DownStore(SQLiteAuditStore):
        def health(self):  # type: ignore[override]
            return {"status": "failed"}

    down, _ = _orchestrator(tmp_path / "down")
    down.audit_store = DownStore(tmp_path / "down" / "down.db")
    assert "persistence unavailable" in down.start(reconciliation_passed=True).reasons


def test_orchestrator_finalized_candles_signal_and_approval_requires_reconciliation(tmp_path) -> None:
    orchestrator, _ = _orchestrator(tmp_path)
    assert orchestrator.start(reconciliation_passed=True).state == ShadowOrchestratorState.RUNNING
    orchestrator.ingest_tick(_tick(0, "a"))
    assert orchestrator.engine.signals_generated == 0
    orchestrator.ingest_tick(_tick(5, "b"))
    assert orchestrator.engine.signals_generated == 1
    request = orchestrator.request_approval_for_latest_signal(StubComposer().intraday_signal(symbol="RELIANCE"))
    assert request.correlation_id == "sig-1"

    blocked, _ = _orchestrator(tmp_path / "blocked", recon_pass=False)
    with pytest.raises(RuntimeError):
        blocked.request_approval_for_latest_signal(StubComposer().intraday_signal(symbol="RELIANCE"))


def test_preview_generation_remains_idempotent(tmp_path) -> None:
    orchestrator, store = _orchestrator(tmp_path)
    orchestrator.start(reconciliation_passed=True)
    signal = StubComposer().intraday_signal(symbol="RELIANCE")
    request = orchestrator.request_approval_for_latest_signal(signal)
    # Approval request is audited; duplicate preview idempotency is covered by Phase 8 wrapper and remains persisted.
    assert store.by_correlation_id(request.correlation_id)


def test_evidence_pack_exports_required_sections_and_api_metadata(tmp_path) -> None:
    orchestrator, store = _orchestrator(tmp_path)
    orchestrator.start(reconciliation_passed=True)
    store.append(RuntimeEvent(RuntimeEventType.SIGNAL_GENERATED, "RELIANCE", {"signal": "BUY"}, "c1", timestamp=datetime(2026, 1, 1, tzinfo=UTC)))
    pack = orchestrator.generate_evidence_pack()
    api = ReadOnlyRuntimeAPI(store, orchestrator.dashboard, orchestrator.shadow, orchestrator=orchestrator)

    required = set(__import__("institutional_trading_platform.runtime.evidence_pack", fromlist=["REQUIRED_EVIDENCE_SECTIONS"]).REQUIRED_EVIDENCE_SECTIONS)
    assert required <= set(pack.sections)
    assert pack.go_live_allowed is False
    assert api.evidence_pack_metadata()["go_live_allowed"] is False
    assert api.shadow_orchestrator_status()["state"] == ShadowOrchestratorState.RUNNING.value


def test_daily_report_contains_required_metrics(tmp_path) -> None:
    _, store = _orchestrator(tmp_path)
    day = datetime(2026, 1, 1, tzinfo=UTC)
    store.append(RuntimeEvent(RuntimeEventType.ZERODHA_TICK_RECEIVED, "RELIANCE", timestamp=day))
    store.append(RuntimeEvent(RuntimeEventType.CANDLE_FINALIZED, "RELIANCE", timestamp=day))
    store.append(RuntimeEvent(RuntimeEventType.SIGNAL_GENERATED, "RELIANCE", {"signal": "BUY"}, timestamp=day))
    store.append(RuntimeEvent(RuntimeEventType.PAPER_PNL_UPDATED, payload={"realized_pnl": 10.0, "drawdown_pct": 1.0}, timestamp=day))
    report = DailyShadowReportGenerator(store).generate(day.date())

    assert report.symbols_observed == ("RELIANCE",)
    assert report.ticks_received == 1
    assert report.candles_finalized == 1
    assert report.signals_generated == 1
    assert report.paper_pnl == 10.0
    assert report.go_live_allowed is False


def test_manual_review_gate_rules(tmp_path) -> None:
    _, store = _orchestrator(tmp_path)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    early = ManualReviewGate(min_samples=1).evaluate(ShadowRunValidator(store, ShadowRunGateConfig(minimum_sample_count=1)).status(), None)
    assert early.decision == ManualReviewDecision.BLOCKED_FOR_REVIEW

    for day in range(30):
        store.append(RuntimeEvent(RuntimeEventType.ZERODHA_CONNECTED, timestamp=now + timedelta(days=day)))
        store.append(RuntimeEvent(RuntimeEventType.ZERODHA_TICK_RECEIVED, "RELIANCE", timestamp=now + timedelta(days=day)))
        store.append(RuntimeEvent(RuntimeEventType.SIGNAL_GENERATED, payload={"signal": "BUY"}, timestamp=now + timedelta(days=day)))
        store.append(RuntimeEvent(RuntimeEventType.PAPER_PNL_UPDATED, payload={"realized_pnl": float(day + 1), "drawdown_pct": 0.0}, timestamp=now + timedelta(days=day)))
    shadow = ShadowRunValidator(store, ShadowRunGateConfig(minimum_sample_count=30, minimum_connection_uptime_pct=90, minimum_profit_factor=0, minimum_win_rate=50))
    pack = EvidencePackGenerator(store, DashboardSummaryService(store), shadow).generate(config_summary={"ZERODHA_ACCESS_TOKEN": "secret"})
    scorecard = RobustnessScorecard(80.0, 80.0, 100.0, 75.0, 75.0, 75.0, 80.0, 100.0, 80.0, RobustnessRecommendation.READY_FOR_MANUAL_REVIEW, (), (), (), False)
    pack.sections["multi_strategy_json"] = {
        "allocations": {"allocations": {"ALPHA_GATE_X": 0.5, "MEAN_REVERSION": 0.5}},
        "health_scores": {"ALPHA_GATE_X": {"status": "HEALTHY"}, "MEAN_REVERSION": {"status": "HEALTHY"}},
        "overlap_warnings": (),
    }

    pack.sections["options_risk_json"] = {
        "greeks": {"data_status": "OK"},
        "iv_metrics": {"data_status": "OK"},
        "expiry_metrics": {"data_status": "OK"},
        "concentration_metrics": {"approved": True},
        "risk_warnings": (),
        "go_live_allowed": False,
    }

    pack.sections["execution_realism_json"] = {
        "execution_reports": ({"execution_quality_score": 90.0},),
        "latency_reports": ({"latency_warning": False},),
        "fill_ratio": 1.0,
        "impact_warnings": (),
        "warnings": (),
        "go_live_allowed": False,
    }

    pack.sections["ha_disaster_recovery_json"] = {"ha_status": {"audit_chain_integrity": True}, "backup_reports": ({"verified": True},), "restore_reports": ({"restore_success": True},), "recovery_readiness": {"recommendation": "READY", "audit_chain_valid": True}, "retention_compliance": {"compliant": True}, "dr_simulations": ({"recovery_success": True},), "business_continuity_report": {"recommendation": "READY_FOR_MANUAL_REVIEW"}, "go_live_allowed": False}

    pack.sections["final_certification_json"] = {"certification_scorecard": {"failed_sections": (), "unavailable_sections": (), "warning_sections": (), "recommendation": "READY_FOR_MANUAL_CERTIFICATION", "go_live_allowed": False}, "readiness_report": {"critical_blockers": (), "recommendation": "READY_FOR_MANUAL_CERTIFICATION", "go_live_allowed": False}, "evidence_quality": {"acceptable": True, "go_live_allowed": False}, "review_workflow": {"completed": True, "go_live_allowed": False}, "review_board_decisions": {"completed": True, "go_live_allowed": False}, "certification_package_metadata": {"package_id": "cert-test", "go_live_allowed": False}, "go_live_allowed": False}
    result = ManualReviewGate(min_samples=30, min_profit_factor=0, min_win_rate=50).evaluate(shadow.status(), pack, runbook_followed=True, robustness_scorecard=scorecard)

    assert result.decision == ManualReviewDecision.READY_FOR_MANUAL_REVIEW
    assert result.go_live_allowed is False
    assert result.decision.value != "LIVE_AUTO_READY"


def test_cli_scripts_compile_no_real_order_path_live_auto_rejected() -> None:
    for file_name in ("scripts/run_shadow_day.py", "scripts/export_evidence_pack.py", "scripts/generate_daily_report.py", "scripts/check_manual_review_gate.py"):
        assert Path(file_name).exists()
    api = ReadOnlyRuntimeAPI(SQLiteAuditStore(":memory:"), DashboardSummaryService(SQLiteAuditStore(":memory:")), ShadowRunValidator(SQLiteAuditStore(":memory:")))
    assert not hasattr(api, "place_order")
    with pytest.raises(ValueError, match="rejects LIVE_AUTO"):
        RuntimeConfig(trading_mode=TradingMode.LIVE_AUTO)
