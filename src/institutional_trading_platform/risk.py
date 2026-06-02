"""Risk and capital allocation utilities for portfolio construction."""

from __future__ import annotations

from math import sqrt
from statistics import fmean


def value_at_risk(returns: list[float], confidence: float = 0.95) -> float:
    """Compute historical Value at Risk as a positive loss value."""

    if not returns:
        raise ValueError("returns cannot be empty")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be between 0 and 1")
    sorted_returns = sorted(returns)
    index = max(0, int((1.0 - confidence) * len(sorted_returns)) - 1)
    return abs(min(sorted_returns[index], 0.0))


def conditional_value_at_risk(returns: list[float], confidence: float = 0.95) -> float:
    """Compute historical Conditional Value at Risk as expected tail loss."""

    var_threshold = -value_at_risk(returns, confidence)
    tail_losses = [return_value for return_value in returns if return_value <= var_threshold]
    if not tail_losses:
        return 0.0
    return abs(fmean(tail_losses))


def fractional_kelly(win_probability: float, win_loss_ratio: float, fraction: float = 0.5) -> float:
    """Return a capped fractional Kelly allocation."""

    if not 0.0 <= win_probability <= 1.0:
        raise ValueError("win_probability must be between 0 and 1")
    if win_loss_ratio <= 0:
        raise ValueError("win_loss_ratio must be positive")
    if not 0.0 <= fraction <= 1.0:
        raise ValueError("fraction must be between 0 and 1")
    full_kelly = win_probability - ((1.0 - win_probability) / win_loss_ratio)
    return max(0.0, min(1.0, full_kelly * fraction))


def annualized_sharpe(returns: list[float], risk_free_rate: float = 0.0, periods: int = 252) -> float:
    """Compute annualized Sharpe ratio from periodic returns."""

    if len(returns) < 2:
        raise ValueError("at least two returns are required")
    excess_returns = [return_value - risk_free_rate / periods for return_value in returns]
    mean_return = fmean(excess_returns)
    variance = sum((return_value - mean_return) ** 2 for return_value in excess_returns) / (
        len(excess_returns) - 1
    )
    volatility = sqrt(variance)
    if volatility == 0:
        return 0.0
    return (mean_return / volatility) * sqrt(periods)
