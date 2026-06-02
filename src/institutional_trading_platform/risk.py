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


def dynamic_value_at_risk(returns: list[float], confidence: float = 0.95, decay: float = 0.94) -> float:
    """Exponentially weighted historical VaR as a positive loss value."""

    if not returns:
        raise ValueError("returns cannot be empty")
    if not 0.0 < confidence < 1.0 or not 0.0 < decay < 1.0:
        raise ValueError("confidence and decay must be in (0, 1)")
    weighted = []
    weight = 1.0
    for return_value in reversed(returns):
        weighted.append((return_value, weight))
        weight *= decay
    total_weight = sum(weight for _, weight in weighted)
    threshold = (1.0 - confidence) * total_weight
    cumulative = 0.0
    for return_value, weight_value in sorted(weighted, key=lambda item: item[0]):
        cumulative += weight_value
        if cumulative >= threshold:
            return abs(min(return_value, 0.0))
    return abs(min(returns))


def dynamic_conditional_value_at_risk(returns: list[float], confidence: float = 0.95, decay: float = 0.94) -> float:
    """Exponentially weighted CVaR as a positive expected tail loss."""

    threshold = -dynamic_value_at_risk(returns, confidence, decay)
    weighted_tail = []
    weight = 1.0
    for return_value in reversed(returns):
        if return_value <= threshold:
            weighted_tail.append((return_value, weight))
        weight *= decay
    if not weighted_tail:
        return 0.0
    return abs(sum(value * weight for value, weight in weighted_tail) / sum(weight for _, weight in weighted_tail))


def stress_test_loss(exposures: dict[str, float], shocks: dict[str, float]) -> float:
    """Portfolio stress-test PnL loss from exposure x shock map."""

    if not exposures:
        raise ValueError("exposures cannot be empty")
    pnl = 0.0
    for asset, exposure in exposures.items():
        pnl += exposure * shocks.get(asset, 0.0)
    return abs(min(pnl, 0.0))


def liquidity_shock(position_quantity: float, average_daily_volume: float, base_slippage_bps: float = 5.0) -> float:
    """Liquidity shock cost in basis points from participation rate."""

    if position_quantity < 0 or average_daily_volume <= 0 or base_slippage_bps < 0:
        raise ValueError("invalid liquidity shock inputs")
    participation = position_quantity / average_daily_volume
    return base_slippage_bps * (1 + participation**0.5)


def correlation_shock_loss(exposures: dict[str, float], shock_correlation: float, volatility: float) -> float:
    """Correlation shock loss approximation for gross exposure."""

    if not 0 <= shock_correlation <= 1 or volatility < 0:
        raise ValueError("invalid correlation shock inputs")
    gross = sum(abs(value) for value in exposures.values())
    return gross * shock_correlation * volatility


def volatility_shock_loss(exposure: float, current_volatility: float, shocked_volatility: float) -> float:
    """Loss estimate from volatility expansion."""

    if current_volatility < 0 or shocked_volatility < 0:
        raise ValueError("volatilities cannot be negative")
    return abs(exposure) * max(0.0, shocked_volatility - current_volatility)


def margin_forecast(gross_exposure: float, volatility: float, base_margin_rate: float = 0.12) -> float:
    """Forecast required margin from exposure and volatility add-on."""

    if gross_exposure < 0 or volatility < 0 or base_margin_rate < 0:
        raise ValueError("margin inputs cannot be negative")
    return gross_exposure * (base_margin_rate + min(1.0, volatility))
