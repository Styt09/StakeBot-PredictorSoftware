from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from institutional_trading_platform.alpha_gate_x import AlphaSignal, TradingMode
from institutional_trading_platform.market_data_spine import TradeRecord
from institutional_trading_platform.runtime import DashboardSummaryService, ManualReviewDecision, ManualReviewGate, RuntimeConfig, RuntimeEvent, RuntimeEventType, ShadowRunGateConfig, ShadowRunValidator, SQLiteAuditStore
from institutional_trading_platform.runtime.evidence_pack import EvidencePackGenerator
from institutional_trading_platform.strategy_orchestration import (
    AllocationMethod,
    CapitalAllocationEngine,
    StrategyCorrelationAnalyzer,
    StrategyHealthScorer,
    StrategyHealthStatus,
    StrategyMetadata,
    StrategyPerformanceTracker,
    StrategyRegime,
    StrategyRegistry,
    StrategyRiskProfile,
    StrategySignal,
    UnifiedSignalAggregator,
    regime_compatibility,
)
from institutional_trading_platform.validation.robustness import RobustnessRecommendation, RobustnessScorecard

UTC = timezone.utc


def _trade(index: int, pnl: float) -> TradeRecord:
    start = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=index)
    return TradeRecord("RELIANCE", AlphaSignal.BUY, start, start + timedelta(minutes=5), 100.0, 101.0, 1, pnl)


def _healthy_context():
    registry = StrategyRegistry()
    registry.register(StrategyMetadata("ALPHA_GATE_X", "Alpha", "1", "Core", ("RELIANCE",), ("5m",), (StrategyRegime.TRENDING,), StrategyRiskProfile.MEDIUM, "intraday"))
    registry.register(StrategyMetadata("MEAN_REVERSION", "MR", "1", "Mean reversion", ("RELIANCE",), ("5m",), (StrategyRegime.RANGING,), StrategyRiskProfile.LOW, "intraday"))
    trades = tuple(_trade(i, 25.0 if i % 4 else -5.0) for i in range(60))
    tracker = StrategyPerformanceTracker()
    perf = {item.strategy_id: tracker.track(item.strategy_id, trades, robustness_score=85.0) for item in registry.all()}
    scorer = StrategyHealthScorer()
    health = {item.strategy_id: scorer.score(item, perf[item.strategy_id]) for item in registry.all()}
    allocation = CapitalAllocationEngine(max_allocation=0.70).allocate(perf, health, method=AllocationMethod.BLENDED)
    corr = StrategyCorrelationAnalyzer().analyze({"ALPHA_GATE_X": (1, -1, 2, -1), "MEAN_REVERSION": (-1, 1, -1, 2)}, {"ALPHA_GATE_X": (AlphaSignal.BUY, AlphaSignal.HOLD), "MEAN_REVERSION": (AlphaSignal.SELL, AlphaSignal.HOLD)}, {"ALPHA_GATE_X": (1, 2), "MEAN_REVERSION": (3, 4)})
    unified = UnifiedSignalAggregator().aggregate((StrategySignal("ALPHA_GATE_X", "RELIANCE", AlphaSignal.BUY, 0.8, 85.0), StrategySignal("MEAN_REVERSION", "RELIANCE", AlphaSignal.HOLD, 0.6, 85.0)), allocation.allocations, health)
    return registry, perf, health, allocation, corr, unified


def test_strategy_registration_and_duplicate_rejection() -> None:
    registry = StrategyRegistry.with_defaults()
    assert registry.get("ALPHA_GATE_X").enabled_flag is True
    with pytest.raises(ValueError, match="already registered"):
        registry.register(registry.get("ALPHA_GATE_X"))


def test_health_score_generation_and_degraded_detection() -> None:
    metadata = StrategyMetadata("MOM", "Momentum", "1", "test", ("RELIANCE",), ("5m",), (StrategyRegime.TRENDING,), StrategyRiskProfile.MEDIUM, "intraday")
    trades = tuple(_trade(i, 20.0) for i in range(30)) + tuple(_trade(30 + i, -25.0) for i in range(20))
    history = StrategyPerformanceTracker().track("MOM", trades, robustness_score=40.0)
    score = StrategyHealthScorer().score(metadata, history)

    assert history.degradation_detected is True
    assert score.status in {StrategyHealthStatus.WATCHLIST, StrategyHealthStatus.DEGRADED, StrategyHealthStatus.DISABLED}


def test_disabled_strategy_allocation_zero_and_caps() -> None:
    registry, perf, health, _, _, _ = _healthy_context()
    disabled = StrategyMetadata("DISABLED", "Off", "1", "off", ("RELIANCE",), ("5m",), (StrategyRegime.TRENDING,), StrategyRiskProfile.LOW, "intraday", enabled_flag=False)
    history = StrategyPerformanceTracker().track("DISABLED", tuple(_trade(i, 5.0) for i in range(20)), robustness_score=80.0)
    perf["DISABLED"] = history
    health["DISABLED"] = StrategyHealthScorer().score(disabled, history)

    report = CapitalAllocationEngine(max_allocation=0.60).allocate(perf, health)
    assert report.allocations["DISABLED"] == 0.0
    assert all(value <= 0.60 for value in report.allocations.values())
    assert report.go_live_allowed is False


def test_regime_compatibility_scoring() -> None:
    trend = StrategyRegistry.with_defaults().get("MOMENTUM")
    assert regime_compatibility(trend, StrategyRegime.TRENDING).score == 1.0
    assert regime_compatibility(trend, StrategyRegime.CHOPPY).score == 0.35


def test_correlation_detection_and_overlap_warning() -> None:
    report = StrategyCorrelationAnalyzer().analyze(
        {"A": (1, 2, 3, 4), "B": (1, 2, 3, 4)},
        {"A": (AlphaSignal.BUY, AlphaSignal.SELL), "B": (AlphaSignal.BUY, AlphaSignal.SELL)},
        {"A": ("t1", "t2"), "B": ("t1", "t2")},
    )
    assert report.pnl_correlation_matrix["A"]["B"] > 0.99
    assert report.overlap_warnings


def test_signal_aggregation_and_conflict_resolution() -> None:
    registry, perf, health, allocation, _, _ = _healthy_context()
    decision = UnifiedSignalAggregator().aggregate(
        (StrategySignal("ALPHA_GATE_X", "RELIANCE", AlphaSignal.BUY, 0.9, 85.0), StrategySignal("MEAN_REVERSION", "RELIANCE", AlphaSignal.SELL, 0.8, 85.0)),
        allocation.allocations,
        health,
    )
    assert decision.signal in {AlphaSignal.BUY, AlphaSignal.SELL, AlphaSignal.HOLD, AlphaSignal.NO_TRADE}
    assert decision.conflict_report.conflict_score > 0
    assert decision.go_live_allowed is False


def test_evidence_pack_integration_and_manual_review_gate_checks() -> None:
    registry, perf, health, allocation, corr, unified = _healthy_context()
    store = SQLiteAuditStore(":memory:")
    now = datetime(2026, 1, 1, tzinfo=UTC)
    for day in range(30):
        store.append(RuntimeEvent(RuntimeEventType.ZERODHA_CONNECTED, timestamp=now + timedelta(days=day)))
        store.append(RuntimeEvent(RuntimeEventType.ZERODHA_TICK_RECEIVED, "RELIANCE", timestamp=now + timedelta(days=day)))
        store.append(RuntimeEvent(RuntimeEventType.SIGNAL_GENERATED, payload={"signal": "BUY"}, timestamp=now + timedelta(days=day)))
        store.append(RuntimeEvent(RuntimeEventType.PAPER_PNL_UPDATED, payload={"realized_pnl": float(day + 1), "drawdown_pct": 0.0}, timestamp=now + timedelta(days=day)))
    shadow = ShadowRunValidator(store, ShadowRunGateConfig(minimum_sample_count=30, minimum_connection_uptime_pct=90, minimum_profit_factor=0, minimum_win_rate=50))
    scorecard = RobustnessScorecard(85, 90, 100, 80, 80, 80, 90, 100, 90, RobustnessRecommendation.READY_FOR_MANUAL_REVIEW, (), (), (), False)
    weak_pack = EvidencePackGenerator(store, DashboardSummaryService(store), shadow).generate(config_summary={}, robustness_scorecard=scorecard)
    weak = ManualReviewGate(min_samples=30, min_profit_factor=0, min_win_rate=50).evaluate(shadow.status(), weak_pack, runbook_followed=True)
    assert weak.decision == ManualReviewDecision.CONTINUE_SHADOW
    assert "strategy_diversification_acceptable" in weak.failure_reasons

    pack = EvidencePackGenerator(store, DashboardSummaryService(store), shadow).generate(
        config_summary={},
        robustness_scorecard=scorecard,
        strategy_registry=registry,
        strategy_health_scores=health,
        strategy_allocation_report=allocation,
        strategy_correlation_report=corr,
        unified_decisions=(unified,),
    )
    assert "multi_strategy_json" in pack.sections
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
    ready = ManualReviewGate(min_samples=30, min_profit_factor=0, min_win_rate=50).evaluate(shadow.status(), pack, runbook_followed=True)
    assert ready.decision == ManualReviewDecision.READY_FOR_MANUAL_REVIEW
    assert ready.go_live_allowed is False


def test_live_auto_rejected_and_no_real_order_path() -> None:
    assert not hasattr(UnifiedSignalAggregator(), "place_order")
    with pytest.raises(ValueError, match="rejects LIVE_AUTO"):
        RuntimeConfig(trading_mode=TradingMode.LIVE_AUTO)
