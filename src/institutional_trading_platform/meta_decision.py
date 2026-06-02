"""Tier 25 meta decision engine."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import fmean
from typing import Mapping, Sequence

from .signal_engine import ApprovalGate, FinalSignalEngine, SignalInput, SignalOutput


@dataclass(frozen=True)
class ModelSignal:
    """Input signal from alpha, ML, RL, LLM, flow, macro, options, or risk models."""

    source: str
    probability: float
    expected_move: float
    confidence: float
    scores: Mapping[str, float]

    def __post_init__(self) -> None:
        if not self.source.strip():
            raise ValueError("source is required")
        if not 0 <= self.probability <= 1 or not 0 <= self.confidence <= 1:
            raise ValueError("probability and confidence must be in [0,1]")
        for score in self.scores.values():
            if not 0 <= score <= 1:
                raise ValueError("scores must be in [0,1]")


@dataclass(frozen=True)
class MetaDecisionInput:
    """Complete meta-decision input across model families and trade construction."""

    model_signals: tuple[ModelSignal, ...]
    base_signal: SignalInput
    gates: tuple[ApprovalGate, ...]
    priors: Mapping[str, float]
    max_conflict: float = 0.35

    def __post_init__(self) -> None:
        if not self.model_signals:
            raise ValueError("model_signals are required")
        if not 0 <= self.max_conflict <= 1:
            raise ValueError("max_conflict must be in [0,1]")


class MetaDecisionEngine:
    """Bayesian aggregation, dynamic weighting, conflict resolution, final approval."""

    def __init__(self, final_signal_engine: FinalSignalEngine | None = None) -> None:
        self.final_signal_engine = final_signal_engine or FinalSignalEngine()

    def evaluate(self, decision_input: MetaDecisionInput) -> SignalOutput:
        """Aggregate model inputs and pass the result through final trade approval."""

        weights = self.dynamic_model_weighting(decision_input.model_signals, decision_input.priors)
        probability = self.bayesian_aggregation(decision_input.model_signals, weights)
        conflict = self.conflict_score(decision_input.model_signals)
        gates = decision_input.gates
        if conflict > decision_input.max_conflict:
            gates = gates + (ApprovalGate("Conflict Resolution", False, "model disagreement exceeds maximum conflict"),)
        aggregated_signal = self._merge_with_base(decision_input.base_signal, decision_input.model_signals, weights, probability)
        return self.final_signal_engine.evaluate(aggregated_signal, gates)

    def bayesian_aggregation(self, signals: Sequence[ModelSignal], weights: Mapping[str, float]) -> float:
        """Weighted posterior probability from model signals."""

        if not signals:
            raise ValueError("signals cannot be empty")
        return sum(signal.probability * weights[signal.source] for signal in signals)

    def dynamic_model_weighting(self, signals: Sequence[ModelSignal], priors: Mapping[str, float]) -> dict[str, float]:
        """Prior x confidence model weights normalized to one."""

        raw = {signal.source: priors.get(signal.source, 1.0) * signal.confidence for signal in signals}
        if any(value < 0 for value in raw.values()) or sum(raw.values()) == 0:
            raise ValueError("model weights must have positive mass")
        total = sum(raw.values())
        return {source: value / total for source, value in raw.items()}

    def conflict_score(self, signals: Sequence[ModelSignal]) -> float:
        """Probability dispersion as model-conflict score."""

        probabilities = [signal.probability for signal in signals]
        mean = fmean(probabilities)
        return max(abs(probability - mean) for probability in probabilities)

    def _merge_with_base(self, base: SignalInput, signals: Sequence[ModelSignal], weights: Mapping[str, float], probability: float) -> SignalInput:
        expected_move = sum(signal.expected_move * weights[signal.source] for signal in signals)
        scores = dict(base.scores)
        for score_name in FinalSignalEngine.REQUIRED_SCORES:
            available = [signal.scores[score_name] for signal in signals if score_name in signal.scores]
            if available:
                scores[score_name] = fmean(available)
        model_votes = {signal.source: signal.confidence for signal in signals}
        return SignalInput(
            expected_move=expected_move,
            expected_sharpe=base.expected_sharpe,
            expected_sortino=base.expected_sortino,
            expected_drawdown=base.expected_drawdown,
            probability_of_profit=base.probability_of_profit,
            bullish_probability=probability,
            bearish_probability=1 - probability,
            entry=base.entry,
            stop_loss=base.stop_loss,
            targets=base.targets,
            dynamic_exit=base.dynamic_exit,
            risk_reward=base.risk_reward,
            position_size=base.position_size,
            capital_allocation=base.capital_allocation,
            scores=scores,
            model_votes=model_votes,
        )
