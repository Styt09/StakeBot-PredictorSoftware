"""Alpha research lab and alpha-science analytics."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, sqrt
from statistics import fmean
from typing import Iterable, Sequence


@dataclass(frozen=True)
class AlphaSignal:
    """Normalized alpha signal with score in [-1, 1]."""

    name: str
    score: float
    confidence: float
    horizon: int

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("alpha name is required")
        if not -1.0 <= self.score <= 1.0:
            raise ValueError("alpha score must be in [-1, 1]")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be in [0, 1]")
        if self.horizon <= 0:
            raise ValueError("horizon must be positive")


def momentum_alpha(prices: Sequence[float], lookback: int) -> AlphaSignal:
    """Price momentum alpha based on lookback return."""

    _require_prices(prices, lookback + 1)
    ret = prices[-1] / prices[-lookback - 1] - 1.0
    return AlphaSignal("momentum", _clip(ret * 10), min(1.0, abs(ret) * 20), lookback)


def mean_reversion_alpha(prices: Sequence[float], lookback: int) -> AlphaSignal:
    """Mean-reversion alpha using z-score distance from recent mean."""

    _require_prices(prices, lookback)
    window = prices[-lookback:]
    mean = fmean(window)
    vol = _sample_std(window)
    z_score = 0.0 if vol == 0 else (prices[-1] - mean) / vol
    return AlphaSignal("mean_reversion", _clip(-z_score / 3.0), min(1.0, abs(z_score) / 3.0), lookback)


def trend_following_alpha(prices: Sequence[float], fast: int, slow: int) -> AlphaSignal:
    """Trend-following alpha from fast/slow moving-average spread."""

    if fast <= 0 or slow <= fast:
        raise ValueError("slow must be greater than fast and both must be positive")
    _require_prices(prices, slow)
    fast_ma = fmean(prices[-fast:])
    slow_ma = fmean(prices[-slow:])
    spread = fast_ma / slow_ma - 1.0
    return AlphaSignal("trend_following", _clip(spread * 20), min(1.0, abs(spread) * 40), slow)


def statistical_arbitrage_alpha(spread: Sequence[float], lookback: int) -> AlphaSignal:
    """Pairs/stat-arb alpha that fades extreme spread z-scores."""

    _require_prices(spread, lookback)
    window = spread[-lookback:]
    mean = fmean(window)
    vol = _sample_std(window)
    z_score = 0.0 if vol == 0 else (spread[-1] - mean) / vol
    return AlphaSignal("statistical_arbitrage", _clip(-z_score / 2.5), min(1.0, abs(z_score) / 2.5), lookback)


def volatility_alpha(realized_volatility: float, implied_volatility: float) -> AlphaSignal:
    """Volatility alpha from implied-realized volatility spread."""

    _positive("realized_volatility", realized_volatility)
    _positive("implied_volatility", implied_volatility)
    edge = implied_volatility - realized_volatility
    return AlphaSignal("volatility", _clip(edge / implied_volatility), min(1.0, abs(edge) / implied_volatility), 21)


def event_driven_alpha(event_surprise: float, historical_event_volatility: float) -> AlphaSignal:
    """Event alpha normalized by historical event volatility."""

    _positive("historical_event_volatility", historical_event_volatility)
    normalized = event_surprise / historical_event_volatility
    return AlphaSignal("event_driven", _clip(normalized / 3.0), min(1.0, abs(normalized) / 3.0), 5)


def cross_asset_alpha(primary_returns: Sequence[float], lead_returns: Sequence[float]) -> AlphaSignal:
    """Cross-asset lead/lag alpha using correlation-adjusted leading return."""

    corr = information_coefficient(primary_returns, lead_returns)
    lead = lead_returns[-1]
    return AlphaSignal("cross_asset", _clip(corr * lead * 25), min(1.0, abs(corr)), 5)


def alternative_data_alpha(sentiment_score: float, confidence: float) -> AlphaSignal:
    """Alternative data alpha from normalized sentiment or activity signal."""

    if not -1 <= sentiment_score <= 1 or not 0 <= confidence <= 1:
        raise ValueError("sentiment_score must be [-1,1] and confidence [0,1]")
    return AlphaSignal("alternative_data", sentiment_score * confidence, confidence, 3)


def options_alpha(skew_signal: float, gamma_pressure: float) -> AlphaSignal:
    """Options alpha combining skew and gamma pressure in normalized units."""

    if not all(isfinite(value) for value in (skew_signal, gamma_pressure)):
        raise ValueError("options inputs must be finite")
    score = _clip((skew_signal + gamma_pressure) / 2.0)
    return AlphaSignal("options", score, min(1.0, abs(score)), 10)


def information_coefficient(predictions: Sequence[float], outcomes: Sequence[float]) -> float:
    """Pearson IC between predictions and realized outcomes."""

    if len(predictions) != len(outcomes) or len(predictions) < 2:
        raise ValueError("predictions and outcomes must have equal length >= 2")
    mean_p = fmean(predictions)
    mean_o = fmean(outcomes)
    cov = sum((p - mean_p) * (o - mean_o) for p, o in zip(predictions, outcomes, strict=True))
    var_p = sum((p - mean_p) ** 2 for p in predictions)
    var_o = sum((o - mean_o) ** 2 for o in outcomes)
    if var_p == 0 or var_o == 0:
        return 0.0
    return cov / sqrt(var_p * var_o)


def ic_decay(prediction_history: Sequence[Sequence[float]], outcome_history: Sequence[Sequence[float]]) -> tuple[float, ...]:
    """IC decay curve across multiple horizons."""

    if len(prediction_history) != len(outcome_history):
        raise ValueError("prediction and outcome histories must align")
    return tuple(information_coefficient(pred, out) for pred, out in zip(prediction_history, outcome_history, strict=True))


def alpha_half_life(ic_values: Sequence[float]) -> int:
    """Return first horizon where IC falls below half the initial absolute IC."""

    if not ic_values:
        raise ValueError("ic_values cannot be empty")
    threshold = abs(ic_values[0]) / 2.0
    for index, value in enumerate(ic_values, start=1):
        if abs(value) <= threshold:
            return index
    return len(ic_values)


def alpha_diversification(signals: Sequence[AlphaSignal]) -> float:
    """Diversification score: high when alpha scores are balanced and non-identical."""

    if len(signals) < 2:
        raise ValueError("at least two signals are required")
    abs_scores = [abs(signal.score) for signal in signals]
    concentration = sum(score**2 for score in abs_scores) / (sum(abs_scores) ** 2) if sum(abs_scores) else 1.0
    return 1.0 - concentration


def alpha_ensemble(signals: Sequence[AlphaSignal]) -> AlphaSignal:
    """Confidence-weighted alpha ensemble."""

    if not signals:
        raise ValueError("signals cannot be empty")
    total_confidence = sum(signal.confidence for signal in signals)
    if total_confidence == 0:
        return AlphaSignal("alpha_ensemble", 0.0, 0.0, max(signal.horizon for signal in signals))
    score = sum(signal.score * signal.confidence for signal in signals) / total_confidence
    confidence = fmean(signal.confidence for signal in signals)
    return AlphaSignal("alpha_ensemble", _clip(score), confidence, max(signal.horizon for signal in signals))


def walk_forward_splits(length: int, train_size: int, test_size: int, step: int | None = None) -> tuple[tuple[range, range], ...]:
    """Generate deterministic walk-forward train/test splits."""

    if min(length, train_size, test_size) <= 0:
        raise ValueError("length, train_size, and test_size must be positive")
    step = test_size if step is None else step
    if step <= 0:
        raise ValueError("step must be positive")
    splits = []
    start = 0
    while start + train_size + test_size <= length:
        splits.append((range(start, start + train_size), range(start + train_size, start + train_size + test_size)))
        start += step
    return tuple(splits)


def purged_k_fold_splits(length: int, folds: int, embargo: int = 0) -> tuple[tuple[tuple[int, ...], tuple[int, ...]], ...]:
    """Generate purged K-fold splits with an embargo around test windows."""

    if length <= 1 or folds < 2 or folds > length or embargo < 0:
        raise ValueError("invalid length/folds/embargo")
    fold_size = length // folds
    splits = []
    indices = tuple(range(length))
    for fold in range(folds):
        start = fold * fold_size
        end = length if fold == folds - 1 else start + fold_size
        test = tuple(range(start, end))
        purge_start = max(0, start - embargo)
        purge_end = min(length, end + embargo)
        train = tuple(index for index in indices if index < purge_start or index >= purge_end)
        splits.append((train, test))
    return tuple(splits)


def combinatorial_purged_cv(length: int, folds: int, test_folds: int, embargo: int = 0) -> tuple[tuple[tuple[int, ...], tuple[int, ...]], ...]:
    """Combinatorial purged CV using combinations of test folds."""

    from itertools import combinations

    if test_folds <= 0 or test_folds >= folds:
        raise ValueError("test_folds must be in [1, folds)")
    base = purged_k_fold_splits(length, folds, embargo)
    all_indices = set(range(length))
    result = []
    for combo in combinations(range(folds), test_folds):
        test = tuple(sorted(index for fold in combo for index in base[fold][1]))
        purge = set(test)
        for index in test:
            purge.update(range(max(0, index - embargo), min(length, index + embargo + 1)))
        train = tuple(sorted(all_indices - purge))
        result.append((train, test))
    return tuple(result)


def _require_prices(values: Sequence[float], minimum_length: int) -> None:
    if len(values) < minimum_length:
        raise ValueError(f"at least {minimum_length} observations are required")
    if not all(isfinite(value) for value in values):
        raise ValueError("observations must be finite")


def _sample_std(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = fmean(values)
    return sqrt(sum((value - mean) ** 2 for value in values) / (len(values) - 1))


def _clip(value: float) -> float:
    return max(-1.0, min(1.0, value))


def _positive(name: str, value: float) -> None:
    if not isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be positive and finite")
