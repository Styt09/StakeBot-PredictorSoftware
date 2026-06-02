"""Regime intelligence and crisis detection."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import exp, isfinite, sqrt
from statistics import fmean
from typing import Mapping, Sequence


class RegimeLabel(StrEnum):
    """Canonical market regime labels."""

    RISK_ON = "RISK_ON"
    RISK_OFF = "RISK_OFF"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_VOLATILITY = "LOW_VOLATILITY"
    ILLIQUID = "ILLIQUID"
    CRISIS = "CRISIS"
    NEUTRAL = "NEUTRAL"


@dataclass(frozen=True)
class RegimeState:
    """Regime classification with probability and component scores."""

    label: RegimeLabel
    probability: float
    volatility_score: float
    liquidity_score: float
    crisis_score: float

    def __post_init__(self) -> None:
        for value in (self.probability, self.volatility_score, self.liquidity_score, self.crisis_score):
            if not 0 <= value <= 1:
                raise ValueError("regime probabilities and scores must be in [0,1]")


def volatility_regime(returns: Sequence[float], high_threshold: float, low_threshold: float) -> RegimeLabel:
    """Classify volatility regime from realized return volatility."""

    realized = realized_volatility(returns)
    if realized >= high_threshold:
        return RegimeLabel.HIGH_VOLATILITY
    if realized <= low_threshold:
        return RegimeLabel.LOW_VOLATILITY
    return RegimeLabel.NEUTRAL


def liquidity_regime(spreads: Sequence[float], depths: Sequence[float], spread_threshold: float, depth_threshold: float) -> RegimeLabel:
    """Classify liquidity regime from spreads and displayed depth."""

    if not spreads or not depths:
        raise ValueError("spreads and depths are required")
    if fmean(spreads) >= spread_threshold or fmean(depths) <= depth_threshold:
        return RegimeLabel.ILLIQUID
    return RegimeLabel.NEUTRAL


def crisis_detection(drawdowns: Sequence[float], volatility: float, liquidity_score: float) -> float:
    """Crisis probability from max drawdown, volatility, and liquidity stress."""

    if not drawdowns or volatility < 0 or not 0 <= liquidity_score <= 1:
        raise ValueError("invalid crisis inputs")
    max_drawdown = max(abs(drawdown) for drawdown in drawdowns)
    raw = 4.0 * max_drawdown + 2.0 * volatility + 1.5 * (1 - liquidity_score)
    return 1 / (1 + exp(-(raw - 1.5)))


def markov_switching_probabilities(transition_matrix: Sequence[Sequence[float]], current_probabilities: Sequence[float]) -> tuple[float, ...]:
    """One-step Markov-switching probability update."""

    n = len(current_probabilities)
    if n == 0 or len(transition_matrix) != n:
        raise ValueError("transition matrix must align with probabilities")
    for row in transition_matrix:
        if len(row) != n or any(value < 0 for value in row) or abs(sum(row) - 1.0) > 1e-6:
            raise ValueError("each transition row must be non-negative and sum to one")
    updated = []
    for to_state in range(n):
        updated.append(sum(current_probabilities[from_state] * transition_matrix[from_state][to_state] for from_state in range(n)))
    total = sum(updated)
    return tuple(value / total for value in updated)


def bayesian_regime_update(priors: Mapping[RegimeLabel, float], likelihoods: Mapping[RegimeLabel, float]) -> dict[RegimeLabel, float]:
    """Bayesian regime posterior from priors and likelihoods."""

    if set(priors) != set(likelihoods) or not priors:
        raise ValueError("priors and likelihoods must cover the same regimes")
    raw = {regime: priors[regime] * likelihoods[regime] for regime in priors}
    if any(value < 0 for value in raw.values()) or sum(raw.values()) == 0:
        raise ValueError("posterior mass must be positive")
    total = sum(raw.values())
    return {regime: value / total for regime, value in raw.items()}


def online_regime_detection(returns: Sequence[float], spreads: Sequence[float], depths: Sequence[float]) -> RegimeState:
    """Detect current regime from recent returns and liquidity observations."""

    vol = realized_volatility(returns)
    normalized_vol = min(1.0, vol / 0.05)
    spread_score = min(1.0, fmean(spreads) / max(max(spreads), 1e-9)) if spreads else 0.0
    depth_score = 1 - min(1.0, fmean(depths) / max(max(depths), 1e-9)) if depths else 1.0
    liquidity_stress = (spread_score + depth_score) / 2.0
    crisis = crisis_detection([min(0.0, value) for value in returns], vol, 1 - liquidity_stress)
    if crisis > 0.7:
        label = RegimeLabel.CRISIS
    elif normalized_vol > 0.7:
        label = RegimeLabel.HIGH_VOLATILITY
    elif liquidity_stress > 0.7:
        label = RegimeLabel.ILLIQUID
    elif fmean(returns) > 0:
        label = RegimeLabel.RISK_ON
    elif fmean(returns) < 0:
        label = RegimeLabel.RISK_OFF
    else:
        label = RegimeLabel.NEUTRAL
    return RegimeState(label, max(normalized_vol, liquidity_stress, crisis), normalized_vol, 1 - liquidity_stress, crisis)


def dynamic_regime_weighting(model_weights: Mapping[str, float], regime_overrides: Mapping[str, float]) -> dict[str, float]:
    """Apply regime-specific model weight multipliers and normalize."""

    if not model_weights:
        raise ValueError("model_weights cannot be empty")
    raw = {model: weight * regime_overrides.get(model, 1.0) for model, weight in model_weights.items()}
    if any(not isfinite(value) or value < 0 for value in raw.values()) or sum(raw.values()) == 0:
        raise ValueError("regime weights must be non-negative and finite")
    total = sum(raw.values())
    return {model: value / total for model, value in raw.items()}


def realized_volatility(returns: Sequence[float]) -> float:
    """Sample realized volatility."""

    if len(returns) < 2:
        raise ValueError("at least two returns are required")
    mean = fmean(returns)
    return sqrt(sum((value - mean) ** 2 for value in returns) / (len(returns) - 1))
