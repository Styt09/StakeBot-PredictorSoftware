"""Machine-learning, ensemble-AI, advanced-AI, LLM, and model-risk primitives."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from math import exp, isfinite, sqrt
from statistics import fmean
from typing import Mapping, Sequence


class ModelFamily(StrEnum):
    """Supported model families across ML, RL, deep learning, and LLM layers."""

    XGBOOST = "XGBoost"
    LIGHTGBM = "LightGBM"
    CATBOOST = "CatBoost"
    RANDOM_FOREST = "Random Forest"
    ONLINE_LEARNING = "Online Learning"
    INCREMENTAL_LEARNING = "Incremental Learning"
    REINFORCEMENT_LEARNING = "Reinforcement Learning"
    DEEP_REINFORCEMENT_LEARNING = "Deep Reinforcement Learning"
    META_LEARNING = "Meta Learning"
    TRANSFER_LEARNING = "Transfer Learning"
    TRANSFORMER = "Transformer"
    TEMPORAL_FUSION_TRANSFORMER = "Temporal Fusion Transformer"
    GRAPH_NEURAL_NETWORK = "Graph Neural Network"
    TEMPORAL_GRAPH_NETWORK = "Temporal Graph Network"
    BAYESIAN_DEEP_LEARNING = "Bayesian Deep Learning"
    PROBABILISTIC_FORECASTING = "Probabilistic Forecasting"
    EXPLAINABLE_AI = "Explainable AI"
    CAUSAL_AI = "Causal AI"
    FINANCIAL_LLM = "Financial LLM"


@dataclass(frozen=True)
class ModelRecord:
    """Governed model registry entry."""

    model_id: str
    family: ModelFamily
    owner: str
    version: str
    feature_names: tuple[str, ...]
    metrics: Mapping[str, float]
    approved: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not all((self.model_id.strip(), self.owner.strip(), self.version.strip())):
            raise ValueError("model_id, owner, and version are required")
        if not self.feature_names:
            raise ValueError("model must declare features")
        for metric_value in self.metrics.values():
            if not isfinite(metric_value):
                raise ValueError("metrics must be finite")


@dataclass(frozen=True)
class ModelPrediction:
    """Normalized model prediction for downstream meta aggregation."""

    model_id: str
    probability: float
    confidence: float
    expected_return: float
    explanation: Mapping[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.model_id.strip():
            raise ValueError("model_id is required")
        if not 0 <= self.probability <= 1 or not 0 <= self.confidence <= 1:
            raise ValueError("probability and confidence must be in [0,1]")
        if not isfinite(self.expected_return):
            raise ValueError("expected_return must be finite")


class ModelRegistry:
    """Model registry with champion/challenger governance."""

    def __init__(self) -> None:
        self._models: dict[str, ModelRecord] = {}
        self._champions: dict[str, str] = {}

    def register(self, model: ModelRecord) -> None:
        """Register or replace a model record."""

        self._models[model.model_id] = model

    def approve(self, model_id: str) -> None:
        """Mark a model as approved by model-risk governance."""

        model = self._models[model_id]
        self._models[model_id] = ModelRecord(
            model_id=model.model_id,
            family=model.family,
            owner=model.owner,
            version=model.version,
            feature_names=model.feature_names,
            metrics=model.metrics,
            approved=True,
            created_at=model.created_at,
        )

    def set_champion(self, use_case: str, model_id: str) -> None:
        """Assign an approved champion model for a use case."""

        if not use_case.strip():
            raise ValueError("use_case is required")
        if not self._models[model_id].approved:
            raise ValueError("champion model must be approved")
        self._champions[use_case] = model_id

    def challengers(self, use_case: str) -> tuple[ModelRecord, ...]:
        """Return approved models except the champion for a use case."""

        champion = self._champions.get(use_case)
        return tuple(model for model in self._models.values() if model.approved and model.model_id != champion)

    def champion(self, use_case: str) -> ModelRecord:
        """Return the champion model for a use case."""

        return self._models[self._champions[use_case]]


def model_stacking(predictions: Sequence[ModelPrediction], meta_weights: Mapping[str, float]) -> ModelPrediction:
    """Weighted stacking using explicit meta-model weights."""

    weights = _weights_for_predictions(predictions, meta_weights)
    return _weighted_prediction("model_stacking", predictions, weights)


def model_blending(predictions: Sequence[ModelPrediction]) -> ModelPrediction:
    """Confidence-weighted model blending."""

    if not predictions:
        raise ValueError("predictions cannot be empty")
    weights = {prediction.model_id: prediction.confidence for prediction in predictions}
    return _weighted_prediction("model_blending", predictions, _normalize(weights))


def bayesian_averaging(predictions: Sequence[ModelPrediction], priors: Mapping[str, float]) -> ModelPrediction:
    """Bayesian model averaging with prior x confidence weights."""

    if not predictions:
        raise ValueError("predictions cannot be empty")
    weights = {prediction.model_id: priors.get(prediction.model_id, 1.0) * prediction.confidence for prediction in predictions}
    return _weighted_prediction("bayesian_averaging", predictions, _normalize(weights))


def dynamic_ensemble_weighting(predictions: Sequence[ModelPrediction], recent_losses: Mapping[str, float]) -> dict[str, float]:
    """Assign larger weights to lower-loss, higher-confidence models."""

    if not predictions:
        raise ValueError("predictions cannot be empty")
    raw = {}
    for prediction in predictions:
        loss = recent_losses.get(prediction.model_id, 1.0)
        if loss < 0:
            raise ValueError("losses cannot be negative")
        raw[prediction.model_id] = prediction.confidence / (loss + 1e-9)
    return _normalize(raw)


def confidence_calibration(probability: float, brier_score: float) -> float:
    """Calibrate confidence downward as Brier score rises."""

    if not 0 <= probability <= 1 or brier_score < 0:
        raise ValueError("invalid probability or brier_score")
    sharpness = abs(probability - 0.5) * 2
    reliability = 1 / (1 + brier_score)
    return max(0.0, min(1.0, sharpness * reliability))


def probabilistic_forecast(mean: float, volatility: float, z_score: float = 1.96) -> tuple[float, float]:
    """Symmetric probabilistic forecast interval."""

    if volatility < 0 or not all(isfinite(value) for value in (mean, volatility, z_score)):
        raise ValueError("forecast inputs must be finite and volatility non-negative")
    return mean - z_score * volatility, mean + z_score * volatility


def feature_attribution(features: Mapping[str, float], coefficients: Mapping[str, float]) -> dict[str, float]:
    """Linear explainability attribution normalized by absolute contribution."""

    missing = [feature for feature in coefficients if feature not in features]
    if missing:
        raise ValueError(f"missing features: {', '.join(missing)}")
    contributions = {feature: features[feature] * coefficients[feature] for feature in coefficients}
    total = sum(abs(value) for value in contributions.values())
    if total == 0:
        return {feature: 0.0 for feature in contributions}
    return {feature: value / total for feature, value in contributions.items()}


def causal_effect(treatment: Sequence[float], outcome: Sequence[float]) -> float:
    """Simple difference-in-means causal effect for binary treatment indicators."""

    if len(treatment) != len(outcome) or not treatment:
        raise ValueError("treatment and outcome must align and be non-empty")
    treated = [y for t, y in zip(treatment, outcome, strict=True) if t == 1]
    control = [y for t, y in zip(treatment, outcome, strict=True) if t == 0]
    if not treated or not control:
        raise ValueError("both treated and control samples are required")
    return fmean(treated) - fmean(control)


def news_intelligence_score(sentiment: float, novelty: float, relevance: float) -> float:
    """Financial LLM/news intelligence score from normalized inputs."""

    if not -1 <= sentiment <= 1 or not 0 <= novelty <= 1 or not 0 <= relevance <= 1:
        raise ValueError("invalid news intelligence inputs")
    return sentiment * novelty * relevance


def earnings_surprise_score(actual: float, consensus: float, historical_surprise_std: float) -> float:
    """Normalize earnings surprise for earnings analysis."""

    if historical_surprise_std <= 0:
        raise ValueError("historical_surprise_std must be positive")
    return (actual - consensus) / historical_surprise_std


def filing_risk_score(risk_terms: Mapping[str, int], materiality_weights: Mapping[str, float]) -> float:
    """Aggregate filing risk terms with materiality weights."""

    score = 0.0
    for term, count in risk_terms.items():
        if count < 0:
            raise ValueError("risk term counts cannot be negative")
        score += count * materiality_weights.get(term, 1.0)
    return score


@dataclass(frozen=True)
class KnowledgeGraphEdge:
    """Financial knowledge graph edge."""

    source: str
    relation: str
    target: str
    confidence: float

    def __post_init__(self) -> None:
        if not all((self.source.strip(), self.relation.strip(), self.target.strip())):
            raise ValueError("source, relation, and target are required")
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be in [0,1]")


def research_summary_score(readability: float, evidence_strength: float, contradiction_penalty: float) -> float:
    """Quality score for LLM-generated research summaries."""

    if not 0 <= readability <= 1 or not 0 <= evidence_strength <= 1 or not 0 <= contradiction_penalty <= 1:
        raise ValueError("summary quality inputs must be in [0,1]")
    return max(0.0, readability * evidence_strength * (1 - contradiction_penalty))


def _weights_for_predictions(predictions: Sequence[ModelPrediction], weights: Mapping[str, float]) -> dict[str, float]:
    if not predictions:
        raise ValueError("predictions cannot be empty")
    missing = [prediction.model_id for prediction in predictions if prediction.model_id not in weights]
    if missing:
        raise ValueError(f"missing weights for: {', '.join(missing)}")
    return _normalize({prediction.model_id: weights[prediction.model_id] for prediction in predictions})


def _normalize(weights: Mapping[str, float]) -> dict[str, float]:
    if not weights:
        raise ValueError("weights cannot be empty")
    for value in weights.values():
        if value < 0 or not isfinite(value):
            raise ValueError("weights must be non-negative finite values")
    total = sum(weights.values())
    if total == 0:
        equal = 1.0 / len(weights)
        return {key: equal for key in weights}
    return {key: value / total for key, value in weights.items()}


def _weighted_prediction(name: str, predictions: Sequence[ModelPrediction], weights: Mapping[str, float]) -> ModelPrediction:
    probability = sum(prediction.probability * weights[prediction.model_id] for prediction in predictions)
    expected_return = sum(prediction.expected_return * weights[prediction.model_id] for prediction in predictions)
    confidence = sum(prediction.confidence * weights[prediction.model_id] for prediction in predictions)
    return ModelPrediction(name, probability, confidence, expected_return)
