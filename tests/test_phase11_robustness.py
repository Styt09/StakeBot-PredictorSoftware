from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from institutional_trading_platform.alpha_gate_x import AlphaSignal, TradingMode
from institutional_trading_platform.market_data_spine import TradeRecord
from institutional_trading_platform.runtime import DashboardSummaryService, ManualReviewDecision, ManualReviewGate, RuntimeConfig, RuntimeEvent, RuntimeEventType, ShadowRunGateConfig, ShadowRunValidator, SQLiteAuditStore
from institutional_trading_platform.runtime.evidence_pack import EvidencePackGenerator
from institutional_trading_platform.validation.robustness import RobustnessRecommendation, RobustnessValidationInput, StrategyRobustnessValidator

UTC = timezone.utc


def _trade(index: int, pnl: float, symbol: str = "RELIANCE", day: int | None = None) -> TradeRecord:
    base = datetime(2026, 1, 1, 9, 15, tzinfo=UTC) + timedelta(days=index if day is None else day)
    return TradeRecord(symbol, AlphaSignal.BUY, base, base + timedelta(minutes=5), 100.0, 100.0 + pnl, 1, pnl)


def _equity(trades: tuple[TradeRecord, ...]) -> tuple[float, ...]:
    curve = [100_000.0]
    for trade in trades:
        curve.append(curve[-1] + trade.pnl)
    return tuple(curve)


def _robust_input(trades: tuple[TradeRecord, ...] | None = None, **overrides) -> RobustnessValidationInput:
    if trades is None:
        trades = tuple(_trade(i, -8.0 if i % 10 in (0, 1) else 25.0, "RELIANCE" if i % 2 else "TCS") for i in range(120))
    data = {
        "trades": trades,
        "equity_curve": _equity(trades),
        "out_of_sample_trades": trades[80:],
        "walk_forward_net_profits": (120.0, 95.0, 80.0),
        "trade_regimes": {i: ("BULLISH_TREND" if i % 3 else "RANGE") for i in range(len(trades))},
        "trade_timeframes": {i: ("5m" if i % 2 else "15m") for i in range(len(trades))},
        "volatility_buckets": {i: ("LOW" if i % 2 else "MEDIUM") for i in range(len(trades))},
        "trend_buckets": {i: ("TREND" if i % 3 else "CHOPPY") for i in range(len(trades))},
        "parameter_results": {"buy_threshold": {0.68: 800.0, 0.72: 850.0, 0.76: 790.0}},
        "no_trade_percentage": 70.0,
        "slippage_bps": 5.0,
        "brokerage_per_trade": 20.0,
    }
    data.update(overrides)
    return RobustnessValidationInput(**data)


def test_low_sample_size_fails_robustness() -> None:
    report = StrategyRobustnessValidator(min_trades=100).validate(_robust_input(tuple(_trade(i, 10.0) for i in range(5))))

    assert report.scorecard.recommendation == RobustnessRecommendation.CONTINUE_VALIDATION
    assert any("too few trades" in check for check in report.scorecard.failed_checks)
    assert report.go_live_allowed is False


def test_one_symbol_and_one_day_profit_concentration_fail() -> None:
    trades = tuple(_trade(i, 20.0, "RELIANCE", day=0) for i in range(120))
    report = StrategyRobustnessValidator(max_profit_concentration_pct=50).validate(_robust_input(trades))

    assert "profits concentrated in one symbol" in report.scorecard.failed_checks
    assert "profits concentrated in one day" in report.scorecard.failed_checks


def test_unstable_profit_factor_warning_appears() -> None:
    trades = tuple(_trade(i, 100.0 if i < 60 else -40.0, "RELIANCE" if i % 2 else "TCS") for i in range(120))
    report = StrategyRobustnessValidator().validate(_robust_input(trades))

    assert any("unstable profit factor" in warning for warning in report.scorecard.warnings)


def test_suspicious_equity_curve_warning_appears() -> None:
    trades = tuple(_trade(i, 5.0, "RELIANCE" if i % 2 else "TCS") for i in range(120))
    report = StrategyRobustnessValidator().validate(_robust_input(trades))

    assert any("suspiciously smooth equity curve" in warning for warning in report.scorecard.warnings)


def test_unrealistic_fill_assumption_warning_blocks_readiness() -> None:
    report = StrategyRobustnessValidator().validate(_robust_input(slippage_bps=0.0))

    assert "unrealistic fill assumptions" in report.scorecard.critical_flags
    assert report.scorecard.recommendation == RobustnessRecommendation.REDESIGN_STRATEGY


@pytest.mark.parametrize("flag", ["lookahead_suspicion", "repainting_suspicion"])
def test_lookahead_and_repainting_suspicion_blocks_readiness(flag: str) -> None:
    report = StrategyRobustnessValidator().validate(_robust_input(**{flag: True}))

    assert report.scorecard.recommendation == RobustnessRecommendation.REDESIGN_STRATEGY
    assert any("suspicion" in item for item in report.scorecard.critical_flags)


def test_robustness_scorecard_allowed_recommendations_only() -> None:
    report = StrategyRobustnessValidator().validate(_robust_input())

    assert report.scorecard.recommendation in set(RobustnessRecommendation)
    assert report.scorecard.recommendation.value != "LIVE_AUTO_READY"
    assert report.scorecard.go_live_allowed is False


def test_evidence_pack_includes_robustness_section() -> None:
    store = SQLiteAuditStore(":memory:")
    report = StrategyRobustnessValidator().validate(_robust_input())
    pack = EvidencePackGenerator(store, DashboardSummaryService(store), ShadowRunValidator(store)).generate(config_summary={"ZERODHA_ACCESS_TOKEN": "secret"}, robustness_report=report)

    robustness = pack.sections["robustness_validation_json"]
    assert robustness["scorecard"]["go_live_allowed"] is False
    assert "symbol_concentration_report" in robustness
    assert "overfitting_warnings" in robustness


def test_manual_review_gate_requires_robustness_pass() -> None:
    store = SQLiteAuditStore(":memory:")
    now = datetime(2026, 1, 1, tzinfo=UTC)
    for day in range(30):
        store.append(RuntimeEvent(RuntimeEventType.ZERODHA_CONNECTED, timestamp=now + timedelta(days=day)))
        store.append(RuntimeEvent(RuntimeEventType.ZERODHA_TICK_RECEIVED, "RELIANCE", timestamp=now + timedelta(days=day)))
        store.append(RuntimeEvent(RuntimeEventType.SIGNAL_GENERATED, payload={"signal": "BUY"}, timestamp=now + timedelta(days=day)))
        store.append(RuntimeEvent(RuntimeEventType.PAPER_PNL_UPDATED, payload={"realized_pnl": float(day + 1), "drawdown_pct": 0.0}, timestamp=now + timedelta(days=day)))
    shadow = ShadowRunValidator(store, ShadowRunGateConfig(minimum_sample_count=30, minimum_connection_uptime_pct=90, minimum_profit_factor=0, minimum_win_rate=50))
    weak_pack = EvidencePackGenerator(store, DashboardSummaryService(store), shadow).generate(config_summary={})
    weak = ManualReviewGate(min_samples=30, min_profit_factor=0, min_win_rate=50).evaluate(shadow.status(), weak_pack, runbook_followed=True)
    assert weak.decision == ManualReviewDecision.CONTINUE_SHADOW
    assert "robustness_score_passed" in weak.failure_reasons

    robust = StrategyRobustnessValidator().validate(_robust_input())
    pack = EvidencePackGenerator(store, DashboardSummaryService(store), shadow).generate(config_summary={}, robustness_report=robust)
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
    ready = ManualReviewGate(min_samples=30, min_profit_factor=0, min_win_rate=50).evaluate(shadow.status(), pack, runbook_followed=True)
    assert ready.decision == ManualReviewDecision.READY_FOR_MANUAL_REVIEW
    assert ready.go_live_allowed is False


def test_live_auto_rejected_and_no_real_order_path_exists() -> None:
    assert not hasattr(StrategyRobustnessValidator(), "place_order")
    with pytest.raises(ValueError, match="rejects LIVE_AUTO"):
        RuntimeConfig(trading_mode=TradingMode.LIVE_AUTO)
