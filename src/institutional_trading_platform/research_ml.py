"""Offline-only research and ML sandbox for ALPHA-GATE X Phase 16.

This module is intentionally advisory-only. It builds research datasets,
tracks feature lineage, records offline experiments, and validates ML evidence
without changing rule-based trading decisions or enabling order placement.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from math import isclose
from typing import Iterable, Mapping, Sequence
from uuid import uuid4

DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
LEAKAGE_COLUMN_HINTS = ("future", "forward", "target", "label", "outcome_after", "next_")


class FeatureAvailabilityStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    DATA_UNAVAILABLE = DATA_UNAVAILABLE


class ResearchRecommendation(StrEnum):
    COLLECT_MORE_DATA = "COLLECT_MORE_DATA"
    REJECT_MODEL = "REJECT_MODEL"
    CONTINUE_RESEARCH = "CONTINUE_RESEARCH"
    READY_FOR_MANUAL_RESEARCH_REVIEW = "READY_FOR_MANUAL_RESEARCH_REVIEW"


@dataclass(frozen=True)
class ResearchDatasetRow:
    timestamp: datetime
    symbol: str
    timeframe: str
    candle: object = DATA_UNAVAILABLE
    signal: object = DATA_UNAVAILABLE
    outcome: object = DATA_UNAVAILABLE
    paper_fill: object = DATA_UNAVAILABLE
    slippage_report: object = DATA_UNAVAILABLE
    execution_quality: object = DATA_UNAVAILABLE
    strategy_metrics: object = DATA_UNAVAILABLE
    regime_label: object = DATA_UNAVAILABLE
    volatility_label: object = DATA_UNAVAILABLE
    portfolio_state: object = DATA_UNAVAILABLE
    options_risk_metrics: object = DATA_UNAVAILABLE

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ResearchDataset:
    dataset_id: str
    rows: tuple[ResearchDatasetRow, ...]
    summary: dict[str, object]
    go_live_allowed: bool = False

    def to_dict(self) -> dict[str, object]:
        return {"dataset_id": self.dataset_id, "rows": tuple(row.to_dict() for row in self.rows), "summary": self.summary, "go_live_allowed": False}


class ResearchDatasetBuilder:
    """Build offline datasets from audit/shadow/paper events without inventing data."""

    REQUIRED_FIELDS = (
        "candle",
        "signal",
        "outcome",
        "paper_fill",
        "slippage_report",
        "execution_quality",
        "strategy_metrics",
        "regime_label",
        "volatility_label",
        "portfolio_state",
        "options_risk_metrics",
    )

    def build_from_events(self, events: Iterable[object], *, dataset_id: str | None = None) -> ResearchDataset:
        rows: list[ResearchDatasetRow] = []
        missing_counts: Counter[str] = Counter()
        for event in events:
            payload = self._payload(event)
            timestamp = self._timestamp(event)
            symbol = str(self._symbol(event, payload))
            timeframe = str(payload.get("timeframe", DATA_UNAVAILABLE))
            values: dict[str, object] = {}
            for field_name in self.REQUIRED_FIELDS:
                value = payload.get(field_name, DATA_UNAVAILABLE)
                if value == DATA_UNAVAILABLE or value is None:
                    value = DATA_UNAVAILABLE
                    missing_counts[field_name] += 1
                values[field_name] = value
            rows.append(ResearchDatasetRow(timestamp=timestamp, symbol=symbol, timeframe=timeframe, **values))
        summary = {
            "row_count": len(rows),
            "missing_fields": dict(missing_counts),
            "symbols": tuple(sorted({row.symbol for row in rows if row.symbol != DATA_UNAVAILABLE})),
            "timeframes": tuple(sorted({row.timeframe for row in rows if row.timeframe != DATA_UNAVAILABLE})),
            "data_status": "OK" if rows else DATA_UNAVAILABLE,
            "go_live_allowed": False,
        }
        return ResearchDataset(dataset_id or f"research-dataset-{uuid4()}", tuple(rows), summary, False)

    @staticmethod
    def _payload(event: object) -> Mapping[str, object]:
        if isinstance(event, Mapping):
            raw = event.get("payload", event)
        else:
            raw = getattr(event, "payload", {})
        return raw if isinstance(raw, Mapping) else {}

    @staticmethod
    def _timestamp(event: object) -> datetime:
        value = event.get("timestamp") if isinstance(event, Mapping) else getattr(event, "timestamp", None)
        if isinstance(value, datetime):
            return value
        return datetime.now(timezone.utc)

    @staticmethod
    def _symbol(event: object, payload: Mapping[str, object]) -> object:
        value = event.get("symbol") if isinstance(event, Mapping) else getattr(event, "symbol", None)
        return value or payload.get("symbol", DATA_UNAVAILABLE)


@dataclass(frozen=True)
class ResearchFeatureRecord:
    feature_name: str
    feature_version: str
    source: str
    timestamp: datetime
    symbol: str
    timeframe: str
    value: object
    availability_status: FeatureAvailabilityStatus = FeatureAvailabilityStatus.AVAILABLE
    lineage: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["availability_status"] = self.availability_status.value
        data["timestamp"] = self.timestamp.isoformat()
        return data


class OfflineFeatureStore:
    """In-memory offline feature store with lineage tracking."""

    def __init__(self) -> None:
        self._features: list[ResearchFeatureRecord] = []

    def register(self, record: ResearchFeatureRecord) -> ResearchFeatureRecord:
        self._features.append(record)
        return record

    def retrieve(self, *, feature_name: str | None = None, symbol: str | None = None, timeframe: str | None = None) -> tuple[ResearchFeatureRecord, ...]:
        records = self._features
        if feature_name is not None:
            records = [record for record in records if record.feature_name == feature_name]
        if symbol is not None:
            records = [record for record in records if record.symbol == symbol]
        if timeframe is not None:
            records = [record for record in records if record.timeframe == timeframe]
        return tuple(records)

    def export(self) -> tuple[dict[str, object], ...]:
        return tuple(record.to_dict() for record in self._features)

    def lineage(self, feature_name: str, feature_version: str | None = None) -> tuple[str, ...]:
        lineage: list[str] = []
        for record in self._features:
            if record.feature_name == feature_name and (feature_version is None or record.feature_version == feature_version):
                lineage.extend(record.lineage)
        return tuple(dict.fromkeys(lineage))

    def availability_summary(self) -> dict[str, object]:
        total = len(self._features)
        unavailable = sum(record.availability_status == FeatureAvailabilityStatus.DATA_UNAVAILABLE for record in self._features)
        return {"total_features": total, "unavailable_features": unavailable, "data_status": "OK" if total else DATA_UNAVAILABLE, "go_live_allowed": False}


@dataclass(frozen=True)
class ResearchExperimentRecord:
    experiment_id: str
    model_type: str
    feature_set_version: str
    train_period: tuple[datetime, datetime]
    validation_period: tuple[datetime, datetime]
    test_period: tuple[datetime, datetime]
    target_definition: str
    metrics: dict[str, float]
    artifact_path: str | None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, object]:
        return {
            "experiment_id": self.experiment_id,
            "model_type": self.model_type,
            "feature_set_version": self.feature_set_version,
            "train_period": tuple(item.isoformat() for item in self.train_period),
            "validation_period": tuple(item.isoformat() for item in self.validation_period),
            "test_period": tuple(item.isoformat() for item in self.test_period),
            "target_definition": self.target_definition,
            "metrics": self.metrics,
            "artifact_path": self.artifact_path,
            "created_at": self.created_at.isoformat(),
            "go_live_allowed": False,
        }


class ExperimentTracker:
    """Local experiment registry. It stores metadata only, not deployable models."""

    def __init__(self) -> None:
        self._records: list[ResearchExperimentRecord] = []

    def record(self, experiment: ResearchExperimentRecord) -> ResearchExperimentRecord:
        self._records.append(experiment)
        return experiment

    def all(self) -> tuple[ResearchExperimentRecord, ...]:
        return tuple(self._records)

    def export(self) -> tuple[dict[str, object], ...]:
        return tuple(record.to_dict() for record in self._records)


@dataclass(frozen=True)
class BaselineComparison:
    majority_class_accuracy: float | str
    random_baseline_accuracy: float | str
    rule_based_accuracy: float | str
    model_metric: float | str
    data_status: str
    go_live_allowed: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class OfflineModelEvaluator:
    """Deterministic baseline evaluator; never fabricates predictive accuracy."""

    @staticmethod
    def majority_class_baseline(labels: Sequence[str]) -> float | str:
        if not labels:
            return DATA_UNAVAILABLE
        counts = Counter(labels)
        return max(counts.values()) / len(labels)

    @staticmethod
    def random_baseline(labels: Sequence[str]) -> float | str:
        if not labels:
            return DATA_UNAVAILABLE
        classes = set(labels)
        return 1.0 / len(classes) if classes else DATA_UNAVAILABLE

    @staticmethod
    def rule_based_baseline(predictions: Sequence[str], labels: Sequence[str]) -> float | str:
        if not predictions or not labels or len(predictions) != len(labels):
            return DATA_UNAVAILABLE
        return sum(pred == label for pred, label in zip(predictions, labels)) / len(labels)

    @staticmethod
    def simple_model_placeholder(features: Sequence[Mapping[str, object]], labels: Sequence[str]) -> str:
        # Explicit placeholder: callers must provide real offline model results via experiment metrics.
        return DATA_UNAVAILABLE if not features or not labels else "OFFLINE_MODEL_REQUIRED"

    def compare(self, labels: Sequence[str], *, rule_predictions: Sequence[str] = (), model_metric: float | None = None) -> BaselineComparison:
        majority = self.majority_class_baseline(labels)
        random = self.random_baseline(labels)
        rule = self.rule_based_baseline(rule_predictions, labels) if rule_predictions else DATA_UNAVAILABLE
        return BaselineComparison(
            majority_class_accuracy=majority,
            random_baseline_accuracy=random,
            rule_based_accuracy=rule,
            model_metric=model_metric if model_metric is not None else DATA_UNAVAILABLE,
            data_status="OK" if labels else DATA_UNAVAILABLE,
            go_live_allowed=False,
        )


@dataclass(frozen=True)
class MLValidationGateResult:
    checks: dict[str, bool]
    class_balance: dict[str, int]
    failure_reasons: tuple[str, ...]
    go_live_allowed: bool = False

    @property
    def passed(self) -> bool:
        return all(self.checks.values())

    def to_dict(self) -> dict[str, object]:
        return {"checks": self.checks, "class_balance": self.class_balance, "failure_reasons": self.failure_reasons, "passed": self.passed, "go_live_allowed": False}


class MLValidationGate:
    """Strict offline-only ML validation checks."""

    def __init__(self, *, min_samples: int = 100, leakage_hints: tuple[str, ...] = LEAKAGE_COLUMN_HINTS) -> None:
        self.min_samples = min_samples
        self.leakage_hints = leakage_hints

    def evaluate(self, *, experiment: ResearchExperimentRecord, feature_names: Sequence[str], labels: Sequence[str], oos_metrics: Mapping[str, float] | None = None, walk_forward_metrics: Mapping[str, float] | None = None, feature_importance: Mapping[str, float] | None = None, regime_metrics: Mapping[str, float] | None = None, calibration_metrics: Mapping[str, float] | None = None) -> MLValidationGateResult:
        leakage_columns = tuple(name for name in feature_names if self._is_leakage_column(name))
        checks = {
            "chronological_split": self._chronological_split(experiment),
            "no_look_ahead_features": not any("future" in name.lower() or "next_" in name.lower() for name in feature_names),
            "no_leakage_columns": not leakage_columns,
            "minimum_sample_size": len(labels) >= self.min_samples,
            "oos_metrics_required": bool(oos_metrics),
            "walk_forward_metrics_required": bool(walk_forward_metrics),
            "feature_importance_sanity": bool(feature_importance) and all(value >= 0 for value in feature_importance.values()),
            "regime_stability": bool(regime_metrics) and (max(regime_metrics.values()) - min(regime_metrics.values()) <= 0.35 if regime_metrics else False),
            "calibration_report_present": bool(calibration_metrics),
        }
        class_balance = dict(Counter(labels))
        failures = list(name for name, passed in checks.items() if not passed)
        if leakage_columns:
            failures.append(f"leakage columns detected: {', '.join(leakage_columns)}")
        return MLValidationGateResult(checks, class_balance, tuple(failures), False)

    def _is_leakage_column(self, name: str) -> bool:
        lowered = name.lower()
        return any(hint in lowered for hint in self.leakage_hints)

    @staticmethod
    def _chronological_split(experiment: ResearchExperimentRecord) -> bool:
        train_start, train_end = experiment.train_period
        validation_start, validation_end = experiment.validation_period
        test_start, test_end = experiment.test_period
        return train_start <= train_end <= validation_start <= validation_end <= test_start <= test_end


@dataclass(frozen=True)
class ModelRiskReport:
    overfitting_risk: str
    leakage_risk: str
    regime_instability_risk: str
    feature_drift_warning: str
    target_leakage_warning: str
    insufficient_sample_warning: str
    suspicious_metric_warning: str
    warnings: tuple[str, ...]
    go_live_allowed: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class ModelRiskReporter:
    """Convert validation failures and metrics into advisory model-risk warnings."""

    def generate(self, validation: MLValidationGateResult, experiments: Sequence[ResearchExperimentRecord], *, feature_drift_detected: bool = False) -> ModelRiskReport:
        metrics = [value for experiment in experiments for value in experiment.metrics.values()]
        suspicious = any(value > 0.98 or (isclose(value, 1.0) and value > 0) for value in metrics)
        warnings: list[str] = []
        if not validation.checks.get("minimum_sample_size", False):
            warnings.append("insufficient sample size")
        if not validation.checks.get("no_leakage_columns", False) or not validation.checks.get("no_look_ahead_features", False):
            warnings.append("potential target/leakage feature detected")
        if not validation.checks.get("regime_stability", False):
            warnings.append("regime instability risk")
        if feature_drift_detected:
            warnings.append("feature drift detected")
        if suspicious:
            warnings.append("suspiciously high metric requires investigation")
        return ModelRiskReport(
            overfitting_risk="HIGH" if suspicious or not validation.checks.get("walk_forward_metrics_required", False) else "LOW",
            leakage_risk="HIGH" if "potential target/leakage feature detected" in warnings else "LOW",
            regime_instability_risk="HIGH" if "regime instability risk" in warnings else "LOW",
            feature_drift_warning="FEATURE_DRIFT_DETECTED" if feature_drift_detected else "OK",
            target_leakage_warning="POTENTIAL_TARGET_LEAKAGE" if "potential target/leakage feature detected" in warnings else "OK",
            insufficient_sample_warning="INSUFFICIENT_SAMPLE" if "insufficient sample size" in warnings else "OK",
            suspicious_metric_warning="SUSPICIOUS_METRIC" if suspicious else "OK",
            warnings=tuple(warnings),
            go_live_allowed=False,
        )


@dataclass(frozen=True)
class ResearchMLReport:
    dataset_summary: dict[str, object]
    feature_availability: dict[str, object]
    experiment_summaries: tuple[dict[str, object], ...]
    baseline_comparison: dict[str, object]
    validation_gate_results: dict[str, object]
    model_risk_report: dict[str, object]
    recommendation: ResearchRecommendation
    go_live_allowed: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "dataset_summary": self.dataset_summary,
            "feature_availability": self.feature_availability,
            "experiment_summaries": self.experiment_summaries,
            "baseline_comparison": self.baseline_comparison,
            "validation_gate_results": self.validation_gate_results,
            "model_risk_report": self.model_risk_report,
            "recommendation": self.recommendation.value,
            "go_live_allowed": False,
            "ml_live_ready": False,
            "ml_override_allowed": False,
        }


class ResearchReportGenerator:
    """Generate advisory-only research reports."""

    def generate(self, *, dataset: ResearchDataset, feature_store: OfflineFeatureStore, experiments: Sequence[ResearchExperimentRecord], baseline: BaselineComparison, validation: MLValidationGateResult, risk_report: ModelRiskReport) -> ResearchMLReport:
        if dataset.summary.get("row_count", 0) == 0 or not validation.checks.get("minimum_sample_size", False):
            recommendation = ResearchRecommendation.COLLECT_MORE_DATA
        elif risk_report.leakage_risk == "HIGH" or "chronological_split" in validation.failure_reasons:
            recommendation = ResearchRecommendation.REJECT_MODEL
        elif validation.passed and not risk_report.warnings:
            recommendation = ResearchRecommendation.READY_FOR_MANUAL_RESEARCH_REVIEW
        elif any("leakage" in reason for reason in validation.failure_reasons):
            recommendation = ResearchRecommendation.REJECT_MODEL
        else:
            recommendation = ResearchRecommendation.CONTINUE_RESEARCH
        return ResearchMLReport(
            dataset_summary=dataset.summary,
            feature_availability=feature_store.availability_summary(),
            experiment_summaries=tuple(experiment.to_dict() for experiment in experiments),
            baseline_comparison=baseline.to_dict(),
            validation_gate_results=validation.to_dict(),
            model_risk_report=risk_report.to_dict(),
            recommendation=recommendation,
            go_live_allowed=False,
        )


def research_ml_evidence_section(report: ResearchMLReport | None) -> dict[str, object]:
    """Evidence-pack section. Missing ML evidence is explicit DATA_UNAVAILABLE, not pass."""

    if report is None:
        return {
            "data_status": DATA_UNAVAILABLE,
            "dataset_summary": {"data_status": DATA_UNAVAILABLE},
            "feature_availability": {"data_status": DATA_UNAVAILABLE},
            "experiment_summaries": (),
            "baseline_comparison": {"data_status": DATA_UNAVAILABLE},
            "validation_gate_results": {"passed": False, "failure_reasons": ("research ML evidence unavailable",)},
            "model_risk_report": {"warnings": ("missing offline research report",)},
            "recommendation": ResearchRecommendation.COLLECT_MORE_DATA.value,
            "go_live_allowed": False,
            "ml_live_ready": False,
            "ml_override_allowed": False,
        }
    return report.to_dict()


def advisory_ml_decision(rule_based_decision: str, ml_recommendation: str | ResearchRecommendation | None = None) -> str:
    """Return the original rule-based decision; ML is advisory and cannot override it."""

    return rule_based_decision
