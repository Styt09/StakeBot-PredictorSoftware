from datetime import UTC, datetime

import pytest

from institutional_trading_platform import (
    ApprovalGate,
    BacktestRecord,
    ExperimentRun,
    Fill,
    FinalSignalEngine,
    GovernanceDecision,
    MetaDecisionEngine,
    MetaDecisionInput,
    ModelFamily,
    ModelPrediction,
    ModelRecord,
    ModelRegistry,
    ModelSignal,
    OptionContract,
    OptionType,
    RegimeLabel,
    ReproducibilityManifest,
    ResearchNotebook,
    ResearchRegistry,
    SignalInput,
    alternative_data_alpha,
    automated_retraining_decision,
    bayesian_averaging,
    black_litterman_weights,
    black_scholes_price,
    capacity_constrained_allocation,
    combinatorial_purged_cv,
    concept_drift_detection,
    crisis_detection,
    cvar_optimization_weights,
    dynamic_conditional_value_at_risk,
    dynamic_value_at_risk,
    earnings_surprise_score,
    feature_attribution,
    gamma_exposure,
    greeks,
    iceberg_schedule,
    information_coefficient,
    liquidity_sweep_score,
    mean_reversion_alpha,
    mean_variance_weights,
    microprice,
    model_blending,
    model_risk_score,
    momentum_alpha,
    online_regime_detection,
    purged_k_fold_splits,
    robust_optimization_weights,
    tca_summary,
    trend_following_alpha,
    twap_schedule,
    vpin,
    vwap_schedule,
)
from institutional_trading_platform.domain import AssetClass, Instrument, OrderBookLevel, OrderBookSnapshot, Venue
from institutional_trading_platform.risk import liquidity_shock, margin_forecast, stress_test_loss


def _manifest() -> ReproducibilityManifest:
    return ReproducibilityManifest(
        git_commit="abc123",
        data_snapshot_id="snapshot-20260602",
        environment={"python": "3.12"},
        parameters={"lookback": "20"},
        random_seed=42,
    )


def _base_signal() -> SignalInput:
    return SignalInput(
        expected_move=0.02,
        expected_sharpe=1.5,
        expected_sortino=1.9,
        expected_drawdown=0.03,
        probability_of_profit=0.64,
        bullish_probability=0.60,
        bearish_probability=0.40,
        entry=100.0,
        stop_loss=97.0,
        targets=(103.0, 106.0, 109.0, 112.0),
        dynamic_exit=101.0,
        risk_reward=3.0,
        position_size=100,
        capital_allocation=0.05,
        scores={score: 0.70 for score in FinalSignalEngine.REQUIRED_SCORES},
    )


def test_research_os_tracks_notebooks_experiments_backtests_approval_and_reproducibility() -> None:
    registry = ResearchRegistry()
    manifest = _manifest()
    registry.register_notebook(ResearchNotebook("nb-1", "research/momentum.ipynb", "quant", "momentum", manifest))
    registry.register_experiment(ExperimentRun("exp-1", "momentum-grid", "quant", {"ic": 0.08}, {"report": "s3://reports/1"}, manifest))
    registry.register_backtest(
        BacktestRecord(
            "bt-1",
            "momentum-v1",
            "quant",
            datetime(2025, 1, 1, tzinfo=UTC),
            datetime(2025, 12, 31, tzinfo=UTC),
            {"sharpe": 1.4},
            manifest,
            lookahead_bias_checked=True,
            survivorship_bias_checked=True,
            data_leakage_checked=True,
        )
    )
    registry.approve("bt-1", "risk-committee", "Bias checks passed")

    assert len(manifest.manifest_hash) == 64
    assert registry.artifact_ids == {"nb-1", "exp-1", "bt-1"}
    assert registry.audit_trail("bt-1")[-1].action == "APPROVED"


def test_alpha_lab_and_alpha_science_cover_core_research_methods() -> None:
    prices = [100, 101, 102, 103, 105, 108]
    momentum = momentum_alpha(prices, 3)
    reversion = mean_reversion_alpha(prices, 4)
    trend = trend_following_alpha(prices, 2, 5)
    alt = alternative_data_alpha(0.6, 0.8)
    ic = information_coefficient([0.1, 0.2, 0.3], [0.01, 0.02, 0.03])

    assert momentum.score > 0
    assert reversion.score < 0
    assert trend.confidence > 0
    assert alt.score == pytest.approx(0.48)
    assert ic == pytest.approx(1.0)
    assert len(purged_k_fold_splits(10, 5, embargo=1)) == 5
    assert len(combinatorial_purged_cv(12, 4, 2, embargo=1)) == 6


def test_microstructure_alpha_vpin_sweeps_and_microprice() -> None:
    instrument = Instrument("RELIANCE", Venue.NSE, AssetClass.EQUITY)
    snapshot = OrderBookSnapshot(
        instrument,
        datetime(2026, 6, 2, tzinfo=UTC),
        bids=(OrderBookLevel(100.0, 300),),
        asks=(OrderBookLevel(100.1, 100),),
        source="unit-test",
    )

    assert vpin([100, 80], [50, 120]) == pytest.approx(90 / 350)
    assert liquidity_sweep_score([100.2, 100.3, 99.9], [100, 100, 50], 100.0) == pytest.approx(0.6)
    assert microprice(snapshot) == pytest.approx(100.075)


def test_ml_ai_registry_ensembles_explainability_and_llm_scores() -> None:
    registry = ModelRegistry()
    model = ModelRecord("xgb-alpha", ModelFamily.XGBOOST, "ml", "1.0", ("mom", "vol"), {"auc": 0.61})
    registry.register(model)
    registry.approve("xgb-alpha")
    registry.set_champion("alpha", "xgb-alpha")

    predictions = (
        ModelPrediction("xgb-alpha", 0.65, 0.8, 0.02),
        ModelPrediction("lgbm-alpha", 0.55, 0.6, 0.01),
    )
    blend = model_blending(predictions)
    bayes = bayesian_averaging(predictions, {"xgb-alpha": 2.0, "lgbm-alpha": 1.0})
    attribution = feature_attribution({"mom": 2.0, "vol": 1.0}, {"mom": 0.5, "vol": -0.25})

    assert registry.champion("alpha").approved
    assert blend.probability > 0.55
    assert bayes.probability > blend.probability
    assert sum(abs(value) for value in attribution.values()) == pytest.approx(1.0)
    assert earnings_surprise_score(120, 100, 10) == pytest.approx(2.0)


def test_regime_derivatives_portfolio_risk_tca_and_governance() -> None:
    state = online_regime_detection([-0.01, -0.02, -0.03, 0.01], [0.01, 0.02], [1000, 900])
    contract = OptionContract(OptionType.CALL, spot=100, strike=100, time_to_expiry=1, volatility=0.2, risk_free_rate=0.01)
    summary = tca_summary(
        fills=(Fill(100.1, 50), Fill(100.2, 50)),
        arrival_price=100.0,
        market_prices=(100.0, 100.1, 100.2),
        market_volumes=(1000, 2000, 1000),
        post_trade_price=100.3,
        side="BUY",
    )

    assert state.label in set(RegimeLabel)
    assert 0 <= crisis_detection([-0.05, -0.1], 0.25, 0.4) <= 1
    assert black_scholes_price(contract) > 0
    assert greeks(contract).gamma > 0
    assert gamma_exposure((contract,), (10,)) > 0
    assert mean_variance_weights({"A": 0.1, "B": 0.05}, {"A": 0.04, "B": 0.01})["B"] > 0
    assert sum(black_litterman_weights({"A": 0.6, "B": 0.4}, {"B": 0.9}, 0.5).values()) == pytest.approx(1.0)
    assert sum(cvar_optimization_weights({"A": 0.1, "B": 0.2}).values()) == pytest.approx(1.0)
    assert sum(robust_optimization_weights(({"A": 0.6, "B": 0.4}, {"A": 0.4, "B": 0.6})).values()) == pytest.approx(1.0)
    assert capacity_constrained_allocation({"A": 0.8, "B": 0.2}, {"A": 50_000}, 100_000)["A"] < 0.8
    assert dynamic_value_at_risk([-0.05, 0.01, -0.02], 0.95) > 0
    assert dynamic_conditional_value_at_risk([-0.05, 0.01, -0.02], 0.95) > 0
    assert stress_test_loss({"A": 1000}, {"A": -0.1}) == pytest.approx(100)
    assert liquidity_shock(1000, 10000) > 5
    assert margin_forecast(100000, 0.2) == pytest.approx(32000)
    assert summary.implementation_shortfall_bps > 0
    assert model_risk_score(0.8, 0.2, 30) > 0
    assert concept_drift_detection(0.8, 0.7, 0.05)
    assert automated_retraining_decision(0.3, 0.25, 0.25, False, 0.2) == GovernanceDecision.APPROVE


def test_execution_algorithms_and_meta_decision_final_approval() -> None:
    assert sum(order.quantity for order in twap_schedule(101, 5)) == 101
    assert sum(order.quantity for order in vwap_schedule(100, (1, 2, 1))) == 100
    assert len(iceberg_schedule(100, 30)) == 4

    gates = tuple(ApprovalGate(name, True) for name in FinalSignalEngine.REQUIRED_GATES)
    model_signals = (
        ModelSignal("alpha", 0.70, 0.03, 0.8, {score: 0.75 for score in FinalSignalEngine.REQUIRED_SCORES}),
        ModelSignal("risk", 0.66, 0.02, 0.7, {score: 0.72 for score in FinalSignalEngine.REQUIRED_SCORES}),
        ModelSignal("llm", 0.62, 0.01, 0.6, {score: 0.70 for score in FinalSignalEngine.REQUIRED_SCORES}),
    )
    output = MetaDecisionEngine().evaluate(MetaDecisionInput(model_signals, _base_signal(), gates, {"alpha": 2.0, "risk": 1.5, "llm": 1.0}))

    assert output.is_tradeable
    assert output.confidence >= 0.55
