"""Derivatives analytics: Greeks, volatility surfaces, forecasting, and calibration."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import erf, exp, isfinite, log, pi, sqrt
from statistics import fmean
from typing import Mapping, Sequence


class OptionType(StrEnum):
    """Option type."""

    CALL = "CALL"
    PUT = "PUT"


@dataclass(frozen=True)
class Greeks:
    """Black-Scholes Greeks."""

    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float


@dataclass(frozen=True)
class OptionContract:
    """Option input for pricing and Greeks."""

    option_type: OptionType
    spot: float
    strike: float
    time_to_expiry: float
    volatility: float
    risk_free_rate: float = 0.0

    def __post_init__(self) -> None:
        for name in ("spot", "strike", "time_to_expiry", "volatility"):
            value = getattr(self, name)
            if not isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be positive and finite")
        if not isfinite(self.risk_free_rate):
            raise ValueError("risk_free_rate must be finite")


def black_scholes_price(contract: OptionContract) -> float:
    """Black-Scholes option price."""

    d1, d2 = _d1_d2(contract)
    if contract.option_type == OptionType.CALL:
        return contract.spot * _cdf(d1) - contract.strike * exp(-contract.risk_free_rate * contract.time_to_expiry) * _cdf(d2)
    return contract.strike * exp(-contract.risk_free_rate * contract.time_to_expiry) * _cdf(-d2) - contract.spot * _cdf(-d1)


def greeks(contract: OptionContract) -> Greeks:
    """Compute Black-Scholes Greeks."""

    d1, d2 = _d1_d2(contract)
    pdf = _pdf(d1)
    sign = 1 if contract.option_type == OptionType.CALL else -1
    delta = _cdf(d1) if contract.option_type == OptionType.CALL else _cdf(d1) - 1
    gamma = pdf / (contract.spot * contract.volatility * sqrt(contract.time_to_expiry))
    theta = -contract.spot * pdf * contract.volatility / (2 * sqrt(contract.time_to_expiry)) - sign * contract.risk_free_rate * contract.strike * exp(-contract.risk_free_rate * contract.time_to_expiry) * _cdf(sign * d2)
    vega = contract.spot * pdf * sqrt(contract.time_to_expiry)
    rho = sign * contract.strike * contract.time_to_expiry * exp(-contract.risk_free_rate * contract.time_to_expiry) * _cdf(sign * d2)
    return Greeks(delta, gamma, theta, vega, rho)


@dataclass(frozen=True)
class VolatilitySurface:
    """Sparse volatility surface indexed by (strike, maturity)."""

    nodes: Mapping[tuple[float, float], float]

    def __post_init__(self) -> None:
        if not self.nodes:
            raise ValueError("surface nodes are required")
        for (strike, maturity), volatility in self.nodes.items():
            if strike <= 0 or maturity <= 0 or volatility <= 0:
                raise ValueError("surface strikes, maturities, and vols must be positive")

    def volatility(self, strike: float, maturity: float) -> float:
        """Nearest-neighbor volatility lookup for sparse calibrated surfaces."""

        if strike <= 0 or maturity <= 0:
            raise ValueError("strike and maturity must be positive")
        nearest = min(self.nodes, key=lambda node: abs(node[0] - strike) + abs(node[1] - maturity))
        return self.nodes[nearest]


def volatility_forecast(realized_volatilities: Sequence[float], decay: float = 0.94) -> float:
    """Exponentially weighted volatility forecast."""

    if not realized_volatilities or not 0 < decay < 1:
        raise ValueError("volatility history and decay in (0,1) are required")
    weight = 1.0
    weighted_sum = 0.0
    total_weight = 0.0
    for volatility in reversed(realized_volatilities):
        if volatility < 0:
            raise ValueError("volatilities cannot be negative")
        weighted_sum += weight * volatility
        total_weight += weight
        weight *= decay
    return weighted_sum / total_weight


def gamma_exposure(contracts: Sequence[OptionContract], quantities: Sequence[int]) -> float:
    """Aggregate gamma exposure across contracts."""

    if len(contracts) != len(quantities) or not contracts:
        raise ValueError("contracts and quantities must align")
    return sum(greeks(contract).gamma * quantity * contract.spot * contract.spot for contract, quantity in zip(contracts, quantities, strict=True))


def variance_swap_fair_strike(volatilities: Sequence[float]) -> float:
    """Variance fair strike from realized vol observations."""

    if not volatilities:
        raise ValueError("volatilities cannot be empty")
    if any(vol < 0 for vol in volatilities):
        raise ValueError("volatilities cannot be negative")
    return fmean(vol * vol for vol in volatilities)


def calibrate_surface(nodes: Mapping[tuple[float, float], float], smoothing: float = 0.0) -> VolatilitySurface:
    """Create a validated surface with optional shrinkage toward mean volatility."""

    if smoothing < 0 or smoothing > 1:
        raise ValueError("smoothing must be in [0,1]")
    mean_vol = fmean(nodes.values())
    smoothed = {node: (1 - smoothing) * vol + smoothing * mean_vol for node, vol in nodes.items()}
    return VolatilitySurface(smoothed)


def _d1_d2(contract: OptionContract) -> tuple[float, float]:
    d1 = (log(contract.spot / contract.strike) + (contract.risk_free_rate + 0.5 * contract.volatility**2) * contract.time_to_expiry) / (contract.volatility * sqrt(contract.time_to_expiry))
    d2 = d1 - contract.volatility * sqrt(contract.time_to_expiry)
    return d1, d2


def _cdf(value: float) -> float:
    return 0.5 * (1 + erf(value / sqrt(2)))


def _pdf(value: float) -> float:
    return exp(-0.5 * value * value) / sqrt(2 * pi)
