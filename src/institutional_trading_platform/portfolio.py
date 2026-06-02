"""Portfolio construction and capital allocation primitives."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from statistics import fmean
from typing import Mapping, Sequence


@dataclass(frozen=True)
class PositionSizingRequest:
    """Inputs for volatility-targeted, risk-budget-aware position sizing."""

    capital: float
    entry_price: float
    stop_loss: float
    risk_budget_fraction: float
    volatility: float
    target_volatility: float
    max_position_fraction: float = 1.0

    def __post_init__(self) -> None:
        for field_name in ("capital", "entry_price", "stop_loss", "risk_budget_fraction", "target_volatility", "max_position_fraction"):
            value = getattr(self, field_name)
            if not isfinite(value) or value <= 0:
                raise ValueError(f"{field_name} must be positive and finite")
        if not isfinite(self.volatility) or self.volatility < 0:
            raise ValueError("volatility must be non-negative and finite")
        if self.entry_price == self.stop_loss:
            raise ValueError("entry_price and stop_loss must differ")
        if self.risk_budget_fraction > 1.0 or self.max_position_fraction > 1.0:
            raise ValueError("risk and max position fractions must be <= 1")


@dataclass(frozen=True)
class PositionSizingResult:
    """Validated position sizing output."""

    quantity: int
    notional: float
    capital_fraction: float
    risk_amount: float


def volatility_targeted_position_size(request: PositionSizingRequest) -> PositionSizingResult:
    """Compute a conservative integer quantity constrained by risk and volatility."""

    risk_per_unit = abs(request.entry_price - request.stop_loss)
    risk_budget = request.capital * request.risk_budget_fraction
    risk_quantity = int(risk_budget / risk_per_unit)
    volatility_scale = 1.0 if request.volatility == 0 else min(1.0, request.target_volatility / request.volatility)
    max_notional = request.capital * request.max_position_fraction * volatility_scale
    notional_quantity = int(max_notional / request.entry_price)
    quantity = max(0, min(risk_quantity, notional_quantity))
    notional = quantity * request.entry_price
    return PositionSizingResult(
        quantity=quantity,
        notional=notional,
        capital_fraction=notional / request.capital,
        risk_amount=quantity * risk_per_unit,
    )


def inverse_volatility_weights(volatilities: Mapping[str, float]) -> dict[str, float]:
    """Return long-only inverse-volatility weights that sum to one."""

    if not volatilities:
        raise ValueError("volatilities cannot be empty")
    inverse_values: dict[str, float] = {}
    for asset, volatility in volatilities.items():
        if not asset.strip():
            raise ValueError("asset names cannot be blank")
        if not isfinite(volatility) or volatility <= 0:
            raise ValueError("volatilities must be positive and finite")
        inverse_values[asset] = 1.0 / volatility
    total = sum(inverse_values.values())
    return {asset: value / total for asset, value in inverse_values.items()}


def equal_risk_contribution_weights(volatilities: Mapping[str, float]) -> dict[str, float]:
    """Alias for diagonal risk-parity weights under zero-correlation assumption."""

    return inverse_volatility_weights(volatilities)


def portfolio_expected_return(weights: Mapping[str, float], expected_returns: Mapping[str, float]) -> float:
    """Compute expected portfolio return after validating coverage."""

    _validate_weights(weights)
    missing = [asset for asset in weights if asset not in expected_returns]
    if missing:
        raise ValueError(f"missing expected returns for: {', '.join(missing)}")
    return sum(weights[asset] * expected_returns[asset] for asset in weights)


def rebalance_trades(current_weights: Mapping[str, float], target_weights: Mapping[str, float], portfolio_value: float) -> dict[str, float]:
    """Compute notional trade list needed to move from current to target weights."""

    _validate_weights(target_weights)
    if not isfinite(portfolio_value) or portfolio_value <= 0:
        raise ValueError("portfolio_value must be positive and finite")
    assets = set(current_weights) | set(target_weights)
    trades = {}
    for asset in sorted(assets):
        current = current_weights.get(asset, 0.0)
        target = target_weights.get(asset, 0.0)
        if current < 0:
            raise ValueError("current weights cannot be negative")
        trades[asset] = (target - current) * portfolio_value
    return trades


def realized_correlation(series_a: Sequence[float], series_b: Sequence[float]) -> float:
    """Compute sample correlation for cross-asset intelligence."""

    if len(series_a) != len(series_b) or len(series_a) < 2:
        raise ValueError("series must have the same length of at least two")
    mean_a = fmean(series_a)
    mean_b = fmean(series_b)
    covariance = sum((a - mean_a) * (b - mean_b) for a, b in zip(series_a, series_b, strict=True))
    variance_a = sum((a - mean_a) ** 2 for a in series_a)
    variance_b = sum((b - mean_b) ** 2 for b in series_b)
    if variance_a == 0 or variance_b == 0:
        return 0.0
    return covariance / (variance_a * variance_b) ** 0.5


def _validate_weights(weights: Mapping[str, float]) -> None:
    if not weights:
        raise ValueError("weights cannot be empty")
    total = 0.0
    for asset, weight in weights.items():
        if not asset.strip():
            raise ValueError("asset names cannot be blank")
        if not isfinite(weight) or weight < 0:
            raise ValueError("weights must be non-negative and finite")
        total += weight
    if abs(total - 1.0) > 1e-6:
        raise ValueError("weights must sum to one")
