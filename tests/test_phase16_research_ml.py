from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from institutional_trading_platform.alpha_gate_x import TradingMode
from institutional_trading_platform.research_ml import (
    DATA_UNAVAILABLE,
    ExperimentTracker,
    FeatureAvailabilityStatus,
    MLValidationGate,
    ModelRiskReporter,
    OfflineFeatureStore,
    OfflineModelEvaluator,
    ResearchDatasetBuilder,
    ResearchExperimentRecord,
    ResearchFeatureRecord,
    ResearchRecommendation,
    ResearchReportGenerator,
    advisory_ml_decision,
)
from institutional_trading_platform.runtime import DashboardSummaryService, InMemoryAuditStore, RuntimeConfig, RuntimeEvent, RuntimeEventType, ShadowRunValidator
from institutional_trading_platform.runtime.api import ReadOnlyRuntimeAPI
from institutional_trading_platform.runtime.evidence_pack import EvidencePackGenerator, REQUIRED_EVIDENCE_SECTIONS

UTC = timezone.utc


def _experiment(*, chronological: bool = True, metric: float = 0.62) -> ResearchExperimentRecord:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    if chronological:
        train = (start, start + timedelta(days=10))
        validation = (start + timedelta(days=11), start + timedelta(days=15))
        test = (start + timedelta(days=16), start + timedelta(days=20))
    else:
        train = (start, start + timedelta(days=20))
        validation = (start + timedelta(days=5), start + timedelta(days=10))
        test = (start + timedelta(days=11), start + timedelta(days=12))
    return ResearchExperimentRecord(
        experiment_id="exp-1",
        model_type="logistic_placeholder",
        feature_set_version="features-v1",
        train_period=train,
        validation_period=validation,
        test_period=test,
        target_definition="next_candle_direction_research_only",
        metrics={"oos_accuracy": metric, "walk_forward_accuracy": metric},
        artifact_path=None,
    )


def test_dataset_builder_marks_missing_fields_unavailable() -> None:
    event = RuntimeEvent(RuntimeEventType.SIGNAL_GENERATED, symbol="RELIANCE", payload={"timeframe": "5m", "signal": "BUY"}, timestamp=datetime(2026, 1, 1, tzinfo=UTC))
    dataset = ResearchDatasetBuilder().build_from_events((event,), dataset_id="ds-1")

    assert dataset.go_live_allowed is False
    assert dataset.rows[0].signal == "BUY"
    assert dataset.rows[0].candle == DATA_UNAVAILABLE
    assert dataset.rows[0].execution_quality == DATA_UNAVAILABLE
    assert dataset.summary["missing_fields"]["candle"] == 1


def test_feature_registration_retrieval_export_and_lineage() -> None:
    store = OfflineFeatureStore()
    record = ResearchFeatureRecord(
        "vwap_distance",
        "v1",
        "paper_candles",
        datetime(2026, 1, 1, tzinfo=UTC),
        "RELIANCE",
        "5m",
        0.12,
        FeatureAvailabilityStatus.AVAILABLE,
        ("audit_events", "candle_builder"),
    )
    store.register(record)

    assert store.retrieve(feature_name="vwap_distance", symbol="RELIANCE") == (record,)
    assert store.lineage("vwap_distance") == ("audit_events", "candle_builder")
    assert store.export()[0]["availability_status"] == "AVAILABLE"


def test_experiment_tracking_and_chronological_split_enforced() -> None:
    tracker = ExperimentTracker()
    experiment = _experiment(chronological=False)
    tracker.record(experiment)
    result = MLValidationGate(min_samples=3).evaluate(
        experiment=experiment,
        feature_names=("vwap_distance", "atr"),
        labels=("UP", "DOWN", "UP"),
        oos_metrics={"accuracy": 0.6},
        walk_forward_metrics={"accuracy": 0.55},
        feature_importance={"vwap_distance": 0.5},
        regime_metrics={"TRENDING": 0.6, "RANGING": 0.55},
        calibration_metrics={"brier": 0.2},
    )

    assert tracker.all() == (experiment,)
    assert result.checks["chronological_split"] is False
    assert "chronological_split" in result.failure_reasons
    assert result.go_live_allowed is False


def test_leakage_columns_and_low_sample_size_fail_validation() -> None:
    result = MLValidationGate(min_samples=10).evaluate(
        experiment=_experiment(),
        feature_names=("future_return_1d", "vwap_distance"),
        labels=("UP", "DOWN"),
        oos_metrics={"accuracy": 0.5},
        walk_forward_metrics={"accuracy": 0.5},
        feature_importance={"future_return_1d": 0.8},
        regime_metrics={"TRENDING": 0.5, "RANGING": 0.5},
        calibration_metrics={"brier": 0.25},
    )

    assert result.checks["no_leakage_columns"] is False
    assert result.checks["minimum_sample_size"] is False
    assert any("future_return_1d" in reason for reason in result.failure_reasons)


def test_baseline_comparison_and_suspicious_metric_warning() -> None:
    evaluator = OfflineModelEvaluator()
    baseline = evaluator.compare(("UP", "UP", "DOWN", "UP"), rule_predictions=("UP", "DOWN", "DOWN", "UP"), model_metric=1.0)
    validation = MLValidationGate(min_samples=3).evaluate(
        experiment=_experiment(metric=1.0),
        feature_names=("vwap_distance", "atr"),
        labels=("UP", "UP", "DOWN", "UP"),
        oos_metrics={"accuracy": 1.0},
        walk_forward_metrics={"accuracy": 1.0},
        feature_importance={"vwap_distance": 0.7},
        regime_metrics={"TRENDING": 1.0, "RANGING": 0.95},
        calibration_metrics={"brier": 0.0},
    )
    risk = ModelRiskReporter().generate(validation, (_experiment(metric=1.0),))

    assert baseline.majority_class_accuracy == 0.75
    assert baseline.rule_based_accuracy == 0.75
    assert risk.suspicious_metric_warning == "SUSPICIOUS_METRIC"
    assert "suspiciously high metric requires investigation" in risk.warnings
    assert risk.go_live_allowed is False


def test_research_report_recommendations_are_allowed_and_go_live_false() -> None:
    dataset = ResearchDatasetBuilder().build_from_events((RuntimeEvent(RuntimeEventType.SIGNAL_GENERATED, payload={"symbol": "RELIANCE"}),))
    store = OfflineFeatureStore()
    experiment = _experiment()
    validation = MLValidationGate(min_samples=10).evaluate(
        experiment=experiment,
        feature_names=("vwap_distance",),
        labels=("UP",),
        oos_metrics={},
        walk_forward_metrics={},
        feature_importance={},
        regime_metrics={},
        calibration_metrics={},
    )
    baseline = OfflineModelEvaluator().compare(("UP",))
    risk = ModelRiskReporter().generate(validation, (experiment,))
    report = ResearchReportGenerator().generate(dataset=dataset, feature_store=store, experiments=(experiment,), baseline=baseline, validation=validation, risk_report=risk)

    assert report.recommendation in set(ResearchRecommendation)
    assert report.recommendation != "ML_LIVE_READY"
    assert report.to_dict()["go_live_allowed"] is False
    assert report.to_dict()["ml_override_allowed"] is False


def test_research_ml_evidence_included_and_missing_ml_is_data_unavailable() -> None:
    store = InMemoryAuditStore()
    pack = EvidencePackGenerator(store, DashboardSummaryService(store), ShadowRunValidator(store)).generate(config_summary={"api_secret": "should-redact"})

    assert "research_ml_json" in REQUIRED_EVIDENCE_SECTIONS
    assert pack.sections["research_ml_json"]["data_status"] == DATA_UNAVAILABLE
    assert pack.sections["research_ml_json"]["go_live_allowed"] is False
    assert "should-redact" not in pack.to_json()


def test_ml_is_advisory_only_and_cannot_override_trading_decision() -> None:
    assert advisory_ml_decision("BUY", ResearchRecommendation.REJECT_MODEL) == "BUY"
    assert advisory_ml_decision("NO_TRADE", ResearchRecommendation.READY_FOR_MANUAL_RESEARCH_REVIEW) == "NO_TRADE"


def test_read_only_research_api_and_no_model_deployment_endpoint() -> None:
    store = InMemoryAuditStore()
    api = ReadOnlyRuntimeAPI(
        store,
        DashboardSummaryService(store),
        ShadowRunValidator(store),
        strategy_context={"research_datasets": {"available": True, "go_live_allowed": False}},
    )

    assert api.research_datasets()["available"] is True
    assert api.research_features()["data_status"] == DATA_UNAVAILABLE
    assert not hasattr(api, "deploy_model")
    assert not hasattr(api, "place_order")


def test_live_auto_rejected_no_real_order_path_and_go_live_false() -> None:
    assert not hasattr(OfflineFeatureStore(), "place_order")
    assert not hasattr(OfflineModelEvaluator(), "place_order")
    with pytest.raises(ValueError, match="rejects LIVE_AUTO"):
        RuntimeConfig(trading_mode=TradingMode.LIVE_AUTO)
