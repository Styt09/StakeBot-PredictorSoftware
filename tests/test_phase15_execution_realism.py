from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from institutional_trading_platform.alpha_gate_x import AlphaSignal, TradingMode
from institutional_trading_platform.execution_simulation import (
    DepthLevel,
    ExecutionMode,
    ExecutionSimulationConfig,
    ExecutionSimulationRequest,
    ExecutionSimulator,
    LatencyBucket,
    LatencyModel,
    OrderBookSnapshot,
    SimulatedOrderType,
    SlippageAssumptions,
    calculate_slippage,
    estimate_market_impact,
    round_to_tick,
)
from institutional_trading_platform.paper_trading import PaperBroker, PaperPortfolio
from institutional_trading_platform.runtime import DashboardSummaryService, ManualReviewDecision, ManualReviewGate, RuntimeConfig, RuntimeEvent, RuntimeEventType, ShadowRunGateConfig, ShadowRunValidator, SQLiteAuditStore
from institutional_trading_platform.runtime.evidence_pack import EvidencePackGenerator
from institutional_trading_platform.validation.robustness import RobustnessRecommendation, RobustnessScorecard

UTC = timezone.utc


def _depth() -> OrderBookSnapshot:
    return OrderBookSnapshot(bids=(DepthLevel(99.95, 10), DepthLevel(99.90, 10)), asks=(DepthLevel(100.05, 10), DepthLevel(100.10, 10)))


def _request(**overrides) -> ExecutionSimulationRequest:
    data = dict(symbol="RELIANCE", side=AlphaSignal.BUY, order_type=SimulatedOrderType.MARKET, quantity=10, reference_price=100.0, average_traded_volume=10_000, volatility=0.2, spread=0.10, depth=_depth())
    data.update(overrides)
    return ExecutionSimulationRequest(**data)


def test_market_order_conservative_fill_and_quality_report() -> None:
    report = ExecutionSimulator().simulate(_request())
    assert report.filled_quantity == 10
    assert report.realized_simulated_price >= 100.0
    assert report.execution_quality_score > 0
    assert report.go_live_allowed is False


def test_limit_order_partial_fill_and_missed_fill() -> None:
    partial = ExecutionSimulator(ExecutionSimulationConfig(mode=ExecutionMode.MICROSTRUCTURE_AWARE)).simulate(_request(order_type=SimulatedOrderType.LIMIT, quantity=20, limit_price=100.05))
    assert partial.filled_quantity == 10
    assert "partial fill" in partial.warnings

    missed = ExecutionSimulator().simulate(_request(order_type=SimulatedOrderType.LIMIT, depth=None, limit_price=99.0))
    assert missed.filled_quantity == 0
    assert missed.realized_simulated_price == "MISSED_FILL"


def test_tick_size_rounding() -> None:
    assert round_to_tick(100.021, 0.05, AlphaSignal.BUY) == 100.05
    assert round_to_tick(100.049, 0.05, AlphaSignal.SELL) == 100.0


def test_latency_calculation_and_bucket() -> None:
    report = LatencyModel(signal_generation_ms=100, order_preparation_ms=200, user_approval_ms=1000, broker_round_trip_ms=1000, websocket_tick_delay_ms=500, candle_finalization_delay_ms=500).report()
    assert report.total_decision_to_fill_ms == 3300
    assert report.latency_bucket == LatencyBucket.CRITICAL
    assert report.latency_warning is True


def test_slippage_models_fixed_volatility_spread_liquidity() -> None:
    report = calculate_slippage(AlphaSignal.BUY, 100.0, 500, 10_000, SlippageAssumptions(fixed_bps=2.0, volatility=0.5, spread=0.20, average_traded_volume=10_000))
    assert report.components["fixed_bps"] == 2.0
    assert report.components["volatility_bps"] > 0
    assert report.components["spread_bps"] > 0
    assert report.components["liquidity_bps"] > 0
    assert report.expected_fill_price > 100.0


def test_market_impact_warning_and_no_depth_unavailable() -> None:
    impact = estimate_market_impact(5_000, 10_000, 100, 0.2, 0.3, 0.10, 100.0)
    assert impact.high_impact_order is True
    assert impact.low_liquidity_order is True
    assert impact.impossible_fill_assumption is True

    no_depth = ExecutionSimulator(ExecutionSimulationConfig(mode=ExecutionMode.MICROSTRUCTURE_AWARE)).simulate(_request(depth=None))
    assert no_depth.data_status == "DATA_UNAVAILABLE"
    assert no_depth.expected_price == "DATA_UNAVAILABLE"


def test_paper_broker_default_conservative() -> None:
    broker = PaperBroker(PaperPortfolio(initial_capital=10_000))
    assert broker.execution_mode == ExecutionMode.CONSERVATIVE


def test_evidence_pack_and_manual_review_execution_gate() -> None:
    store = SQLiteAuditStore(":memory:")
    now = datetime(2026, 1, 1, tzinfo=UTC)
    for day in range(30):
        store.append(RuntimeEvent(RuntimeEventType.ZERODHA_CONNECTED, timestamp=now + timedelta(days=day)))
        store.append(RuntimeEvent(RuntimeEventType.ZERODHA_TICK_RECEIVED, "RELIANCE", timestamp=now + timedelta(days=day)))
        store.append(RuntimeEvent(RuntimeEventType.SIGNAL_GENERATED, payload={"signal": "BUY"}, timestamp=now + timedelta(days=day)))
        store.append(RuntimeEvent(RuntimeEventType.PAPER_PNL_UPDATED, payload={"realized_pnl": float(day + 1), "drawdown_pct": 0.0}, timestamp=now + timedelta(days=day)))
    shadow = ShadowRunValidator(store, ShadowRunGateConfig(minimum_sample_count=30, minimum_connection_uptime_pct=90, minimum_profit_factor=0, minimum_win_rate=50))
    execution_report = ExecutionSimulator().simulate(_request())
    pack = EvidencePackGenerator(store, DashboardSummaryService(store), shadow).generate(config_summary={}, execution_reports=(execution_report,), execution_assumptions={"mode": "CONSERVATIVE"})
    pack.sections["robustness_validation_json"] = {"scorecard": RobustnessScorecard(85, 90, 100, 80, 80, 80, 90, 100, 90, RobustnessRecommendation.READY_FOR_MANUAL_REVIEW, (), (), (), False).to_dict()}
    pack.sections["multi_strategy_json"] = {"allocations": {"allocations": {"A": 0.5, "B": 0.5}}, "health_scores": {"A": {"status": "HEALTHY"}, "B": {"status": "HEALTHY"}}, "overlap_warnings": ()}
    pack.sections["options_risk_json"] = {"greeks": {"data_status": "OK"}, "iv_metrics": {"data_status": "OK"}, "expiry_metrics": {"data_status": "OK"}, "concentration_metrics": {"approved": True}, "risk_warnings": (), "go_live_allowed": False}

    pack.sections["ha_disaster_recovery_json"] = {"ha_status": {"audit_chain_integrity": True}, "backup_reports": ({"verified": True},), "restore_reports": ({"restore_success": True},), "recovery_readiness": {"recommendation": "READY", "audit_chain_valid": True}, "retention_compliance": {"compliant": True}, "dr_simulations": ({"recovery_success": True},), "business_continuity_report": {"recommendation": "READY_FOR_MANUAL_REVIEW"}, "go_live_allowed": False}

    pack.sections["final_certification_json"] = {"certification_scorecard": {"failed_sections": (), "unavailable_sections": (), "warning_sections": (), "recommendation": "READY_FOR_MANUAL_CERTIFICATION", "go_live_allowed": False}, "readiness_report": {"critical_blockers": (), "recommendation": "READY_FOR_MANUAL_CERTIFICATION", "go_live_allowed": False}, "evidence_quality": {"acceptable": True, "go_live_allowed": False}, "review_workflow": {"completed": True, "go_live_allowed": False}, "review_board_decisions": {"completed": True, "go_live_allowed": False}, "certification_package_metadata": {"package_id": "cert-test", "go_live_allowed": False}, "go_live_allowed": False}
    ready = ManualReviewGate(min_samples=30, min_profit_factor=0, min_win_rate=50).evaluate(shadow.status(), pack, runbook_followed=True)
    assert pack.sections["execution_realism_json"]["go_live_allowed"] is False
    assert ready.decision == ManualReviewDecision.READY_FOR_MANUAL_REVIEW
    assert ready.go_live_allowed is False


def test_live_auto_rejected_and_no_real_order_path() -> None:
    assert not hasattr(ExecutionSimulator(), "place_order")
    with pytest.raises(ValueError, match="rejects LIVE_AUTO"):
        RuntimeConfig(trading_mode=TradingMode.LIVE_AUTO)
