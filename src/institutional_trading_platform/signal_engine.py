"""Final Signal Engine v8.0.

The engine implements the platform's strict rule: trade only when every
institutional gate has approved the opportunity; otherwise return NO TRADE.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from statistics import fmean


class MarketDecision(StrEnum):
    """Allowed final trading decisions."""

    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    NO_TRADE = "NO TRADE"


@dataclass(frozen=True)
class ApprovalGate:
    """A mandatory pre-trade approval gate."""

    name: str
    approved: bool
    reason: str = ""


@dataclass(frozen=True)
class SignalInput:
    """Normalized model, risk, execution, and portfolio inputs."""

    expected_move: float
    expected_sharpe: float
    expected_sortino: float
    expected_drawdown: float
    probability_of_profit: float
    bullish_probability: float
    bearish_probability: float
    entry: float
    stop_loss: float
    targets: tuple[float, float, float, float]
    dynamic_exit: float
    risk_reward: float
    position_size: float
    capital_allocation: float
    scores: dict[str, float]
    model_votes: dict[str, float] = field(default_factory=dict)

    def validate(self) -> None:
        """Validate financial ranges before a signal can be evaluated."""

        probability_fields = {
            "probability_of_profit": self.probability_of_profit,
            "bullish_probability": self.bullish_probability,
            "bearish_probability": self.bearish_probability,
        }
        for field_name, value in probability_fields.items():
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{field_name} must be between 0 and 1")

        for score_name, value in self.scores.items():
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{score_name} score must be between 0 and 1")

        if len(self.targets) != 4:
            raise ValueError("targets must contain exactly four price objectives")
        if self.entry <= 0 or self.stop_loss <= 0 or self.dynamic_exit <= 0:
            raise ValueError("entry, stop_loss, and dynamic_exit must be positive")
        if self.position_size < 0 or self.capital_allocation < 0:
            raise ValueError("position_size and capital_allocation cannot be negative")


@dataclass(frozen=True)
class SignalOutput:
    """Decision payload produced by the final signal engine."""

    decision: MarketDecision
    confidence: float
    bullish_probability: float
    bearish_probability: float
    expected_move: float
    expected_sharpe: float
    expected_sortino: float
    expected_drawdown: float
    probability_of_profit: float
    scores: dict[str, float]
    entry: float | None
    stop_loss: float | None
    targets: tuple[float, float, float, float] | None
    dynamic_exit: float | None
    risk_reward: float
    position_size: float
    capital_allocation: float
    rejected_gates: tuple[ApprovalGate, ...]

    @property
    def is_tradeable(self) -> bool:
        """Return whether this output may be routed to execution."""

        return self.decision in {MarketDecision.BUY, MarketDecision.SELL}


class FinalSignalEngine:
    """Governance-first decision engine for v8.0 final trade approval."""

    REQUIRED_GATES: tuple[str, ...] = (
        "Data Approved",
        "Research Approved",
        "Alpha Approved",
        "Regime Confirmed",
        "Liquidity Approved",
        "Spread Approved",
        "Volume Approved",
        "Trend Approved",
        "Price Action Approved",
        "Market Structure Approved",
        "Flow Approved",
        "Options Approved",
        "Futures Approved",
        "Sentiment Approved",
        "Macro Approved",
        "Risk Approved",
        "Compliance Approved",
        "Portfolio Approved",
        "Execution Approved",
        "AI Consensus Approved",
    )

    REQUIRED_SCORES: tuple[str, ...] = (
        "alpha",
        "regime",
        "technical",
        "flow",
        "sentiment",
        "macro",
        "options",
        "risk",
        "execution",
        "liquidity",
        "portfolio_impact",
    )

    def __init__(self, minimum_confidence: float = 0.55, minimum_score: float = 0.50) -> None:
        if not 0.0 <= minimum_confidence <= 1.0:
            raise ValueError("minimum_confidence must be between 0 and 1")
        if not 0.0 <= minimum_score <= 1.0:
            raise ValueError("minimum_score must be between 0 and 1")
        self.minimum_confidence = minimum_confidence
        self.minimum_score = minimum_score

    def evaluate(self, signal_input: SignalInput, gates: tuple[ApprovalGate, ...]) -> SignalOutput:
        """Evaluate the signal and return BUY, SELL, HOLD, or NO TRADE."""

        signal_input.validate()
        gate_map = {gate.name: gate for gate in gates}
        rejected_gates = self._rejected_gates(gate_map)
        missing_scores = [score for score in self.REQUIRED_SCORES if score not in signal_input.scores]
        confidence = self._confidence(signal_input)

        score_rejections = tuple(
            ApprovalGate(self._score_gate_name(score), False, "score below minimum threshold")
            for score in self.REQUIRED_SCORES
            if score in signal_input.scores and signal_input.scores[score] < self.minimum_score
        )
        missing_score_rejections = tuple(
            ApprovalGate(self._score_gate_name(score), False, "required score is missing")
            for score in missing_scores
        )
        rejected_gates = rejected_gates + score_rejections + missing_score_rejections

        if rejected_gates or confidence < self.minimum_confidence:
            confidence_rejections = ()
            if confidence < self.minimum_confidence:
                confidence_rejections = (
                    ApprovalGate("Confidence Calibration", False, "confidence below threshold"),
                )
            return self._blocked_output(signal_input, confidence, rejected_gates + confidence_rejections)

        return SignalOutput(
            decision=self._direction(signal_input),
            confidence=confidence,
            bullish_probability=signal_input.bullish_probability,
            bearish_probability=signal_input.bearish_probability,
            expected_move=signal_input.expected_move,
            expected_sharpe=signal_input.expected_sharpe,
            expected_sortino=signal_input.expected_sortino,
            expected_drawdown=signal_input.expected_drawdown,
            probability_of_profit=signal_input.probability_of_profit,
            scores=dict(signal_input.scores),
            entry=signal_input.entry,
            stop_loss=signal_input.stop_loss,
            targets=signal_input.targets,
            dynamic_exit=signal_input.dynamic_exit,
            risk_reward=signal_input.risk_reward,
            position_size=signal_input.position_size,
            capital_allocation=signal_input.capital_allocation,
            rejected_gates=(),
        )

    def _rejected_gates(self, gate_map: dict[str, ApprovalGate]) -> tuple[ApprovalGate, ...]:
        rejected: list[ApprovalGate] = []
        for required_gate in self.REQUIRED_GATES:
            gate = gate_map.get(required_gate)
            if gate is None:
                rejected.append(ApprovalGate(required_gate, False, "required approval is missing"))
            elif not gate.approved:
                rejected.append(gate)
        return tuple(rejected)

    def _score_gate_name(self, score: str) -> str:
        return f"{score.replace('_', ' ').title()} Score"

    def _confidence(self, signal_input: SignalInput) -> float:
        directional_confidence = max(
            signal_input.bullish_probability,
            signal_input.bearish_probability,
            signal_input.probability_of_profit,
        )
        required_score_values = [signal_input.scores.get(score, 0.0) for score in self.REQUIRED_SCORES]
        score_confidence = fmean(required_score_values)
        model_confidence = fmean(signal_input.model_votes.values()) if signal_input.model_votes else score_confidence
        return round(fmean((directional_confidence, score_confidence, model_confidence)), 4)

    def _direction(self, signal_input: SignalInput) -> MarketDecision:
        if abs(signal_input.bullish_probability - signal_input.bearish_probability) < 0.05:
            return MarketDecision.HOLD
        if signal_input.bullish_probability > signal_input.bearish_probability:
            return MarketDecision.BUY
        return MarketDecision.SELL

    def _blocked_output(
        self,
        signal_input: SignalInput,
        confidence: float,
        rejected_gates: tuple[ApprovalGate, ...],
    ) -> SignalOutput:
        return SignalOutput(
            decision=MarketDecision.NO_TRADE,
            confidence=confidence,
            bullish_probability=signal_input.bullish_probability,
            bearish_probability=signal_input.bearish_probability,
            expected_move=signal_input.expected_move,
            expected_sharpe=signal_input.expected_sharpe,
            expected_sortino=signal_input.expected_sortino,
            expected_drawdown=signal_input.expected_drawdown,
            probability_of_profit=signal_input.probability_of_profit,
            scores=dict(signal_input.scores),
            entry=None,
            stop_loss=None,
            targets=None,
            dynamic_exit=None,
            risk_reward=0.0,
            position_size=0.0,
            capital_allocation=0.0,
            rejected_gates=rejected_gates,
        )
