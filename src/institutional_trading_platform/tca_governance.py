"""Transaction cost analysis and enterprise governance controls."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from statistics import fmean
from typing import Mapping, Sequence


class GovernanceDecision(StrEnum):
    """Governance and compliance decision."""

    APPROVE = "APPROVE"
    REJECT = "REJECT"
    ESCALATE = "ESCALATE"


@dataclass(frozen=True)
class Fill:
    """Execution fill for TCA and reconciliation."""

    price: float
    quantity: int
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if self.price <= 0 or self.quantity <= 0:
            raise ValueError("fill price and quantity must be positive")


@dataclass(frozen=True)
class TCASummary:
    """Transaction cost analysis summary in basis points."""

    average_fill_price: float
    implementation_shortfall_bps: float
    vwap_slippage_bps: float
    twap_slippage_bps: float
    market_impact_bps: float


def average_fill_price(fills: Sequence[Fill]) -> float:
    """Quantity-weighted average fill price."""

    if not fills:
        raise ValueError("fills cannot be empty")
    total_quantity = sum(fill.quantity for fill in fills)
    return sum(fill.price * fill.quantity for fill in fills) / total_quantity


def implementation_shortfall(arrival_price: float, average_price: float, side: str) -> float:
    """Implementation shortfall in basis points; positive is worse."""

    sign = _side_sign(side)
    return sign * (average_price - arrival_price) / arrival_price * 10_000


def benchmark_slippage(average_price: float, benchmark_price: float, side: str) -> float:
    """VWAP/TWAP benchmark slippage in basis points; positive is worse."""

    sign = _side_sign(side)
    return sign * (average_price - benchmark_price) / benchmark_price * 10_000


def vwap_benchmark(prices: Sequence[float], volumes: Sequence[float]) -> float:
    """VWAP benchmark."""

    if len(prices) != len(volumes) or not prices:
        raise ValueError("prices and volumes must align")
    total_volume = sum(volumes)
    if total_volume <= 0:
        raise ValueError("total volume must be positive")
    return sum(price * volume for price, volume in zip(prices, volumes, strict=True)) / total_volume


def twap_benchmark(prices: Sequence[float]) -> float:
    """TWAP benchmark."""

    if not prices:
        raise ValueError("prices cannot be empty")
    return fmean(prices)


def market_impact_attribution(arrival_price: float, post_trade_price: float, side: str) -> float:
    """Market impact in basis points; positive is adverse."""

    sign = _side_sign(side)
    return sign * (post_trade_price - arrival_price) / arrival_price * 10_000


def tca_summary(fills: Sequence[Fill], arrival_price: float, market_prices: Sequence[float], market_volumes: Sequence[float], post_trade_price: float, side: str) -> TCASummary:
    """Full TCA summary from fills and benchmark data."""

    avg = average_fill_price(fills)
    vwap = vwap_benchmark(market_prices, market_volumes)
    twap = twap_benchmark(market_prices)
    return TCASummary(
        average_fill_price=avg,
        implementation_shortfall_bps=implementation_shortfall(arrival_price, avg, side),
        vwap_slippage_bps=benchmark_slippage(avg, vwap, side),
        twap_slippage_bps=benchmark_slippage(avg, twap, side),
        market_impact_bps=market_impact_attribution(arrival_price, post_trade_price, side),
    )


def pre_trade_compliance(order_notional: float, restricted: bool, max_notional: float) -> GovernanceDecision:
    """Pre-trade compliance decision."""

    if restricted or order_notional > max_notional:
        return GovernanceDecision.REJECT
    return GovernanceDecision.APPROVE


def surveillance_score(cancel_rate: float, self_trade_count: int, price_deviation_bps: float) -> float:
    """Composite market-abuse surveillance risk score in [0, 1]."""

    if cancel_rate < 0 or self_trade_count < 0 or price_deviation_bps < 0:
        raise ValueError("surveillance inputs cannot be negative")
    return min(1.0, cancel_rate * 0.4 + min(1.0, self_trade_count / 10) * 0.3 + min(1.0, price_deviation_bps / 100) * 0.3)


def model_risk_score(validation_metric: float, drift_score: float, age_days: int) -> float:
    """Model risk score in [0,1], where higher means riskier."""

    if not 0 <= validation_metric <= 1 or not 0 <= drift_score <= 1 or age_days < 0:
        raise ValueError("invalid model-risk inputs")
    performance_risk = 1 - validation_metric
    age_risk = min(1.0, age_days / 365)
    return performance_risk * 0.45 + drift_score * 0.35 + age_risk * 0.20


def concept_drift_detection(baseline_accuracy: float, recent_accuracy: float, tolerance: float) -> bool:
    """Detect concept drift by degradation beyond tolerance."""

    if not 0 <= baseline_accuracy <= 1 or not 0 <= recent_accuracy <= 1 or tolerance < 0:
        raise ValueError("invalid concept drift inputs")
    return baseline_accuracy - recent_accuracy > tolerance


def automated_retraining_decision(data_drift: float, model_drift: float, feature_drift: float, concept_drift: bool, threshold: float = 0.25) -> GovernanceDecision:
    """Decide whether automated retraining should be triggered or escalated."""

    if any(value < 0 for value in (data_drift, model_drift, feature_drift, threshold)):
        raise ValueError("drift scores cannot be negative")
    aggregate = fmean((data_drift, model_drift, feature_drift, 1.0 if concept_drift else 0.0))
    if aggregate >= threshold * 2:
        return GovernanceDecision.ESCALATE
    if aggregate >= threshold:
        return GovernanceDecision.APPROVE
    return GovernanceDecision.REJECT


def reconciliation_breaks(expected: Mapping[str, float], actual: Mapping[str, float], tolerance: float = 1e-6) -> dict[str, float]:
    """Position/holding/trade reconciliation breaks by key."""

    if tolerance < 0:
        raise ValueError("tolerance cannot be negative")
    breaks = {}
    for key in sorted(set(expected) | set(actual)):
        difference = actual.get(key, 0.0) - expected.get(key, 0.0)
        if abs(difference) > tolerance:
            breaks[key] = difference
    return breaks


def resilience_recovery_point(last_snapshot_sequence: int, replayed_event_sequence: int) -> bool:
    """Validate event-sourcing replay recovered through latest event."""

    if last_snapshot_sequence < 0 or replayed_event_sequence < 0:
        raise ValueError("sequences cannot be negative")
    return replayed_event_sequence >= last_snapshot_sequence


def _side_sign(side: str) -> int:
    normalized = side.upper()
    if normalized == "BUY":
        return 1
    if normalized == "SELL":
        return -1
    raise ValueError("side must be BUY or SELL")
