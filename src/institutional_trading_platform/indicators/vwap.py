"""VWAP indicators for ALPHA-GATE X."""

from __future__ import annotations

from collections.abc import Sequence

from ..market_data_spine import DataQualityStatus, OHLCVCandle
from .common import IndicatorResult, clamp_score, unavailable


def typical_price(candle: OHLCVCandle) -> float:
    """Return candle typical price."""

    return (candle.high + candle.low + candle.close) / 3.0


def session_vwap(candles: Sequence[OHLCVCandle]) -> float | None:
    """Calculate session VWAP over completed candles."""

    completed = [candle for candle in candles if candle.complete]
    volume = sum(candle.volume for candle in completed)
    if not completed or volume <= 0:
        return None
    return sum(typical_price(candle) * candle.volume for candle in completed) / volume


def rolling_vwap(candles: Sequence[OHLCVCandle], period: int = 20) -> float | None:
    """Calculate rolling VWAP for the last ``period`` completed candles."""

    if period <= 0:
        raise ValueError("period must be positive")
    completed = [candle for candle in candles if candle.complete]
    if len(completed) < period:
        return None
    return session_vwap(completed[-period:])


def vwap_distance_percent(price: float, vwap: float) -> float:
    """Return price distance from VWAP in percent."""

    if price <= 0 or vwap <= 0:
        raise ValueError("price and vwap must be positive")
    return ((price - vwap) / vwap) * 100.0


def vwap_pressure_score(candles: Sequence[OHLCVCandle], period: int = 3) -> IndicatorResult:
    """Score VWAP pressure from -1 to +1 using real completed candles."""

    completed = [candle for candle in candles if candle.complete]
    if len(completed) < period:
        return unavailable("vwap_pressure", "insufficient completed candles for VWAP")
    vwap = session_vwap(completed)
    if vwap is None:
        return unavailable("vwap_pressure", "VWAP unavailable because completed volume is zero")
    latest = completed[-1]
    avg_volume = sum(candle.volume for candle in completed[-period:]) / period
    volume_ratio = latest.volume / avg_volume if avg_volume > 0 else 0.0
    distance = vwap_distance_percent(latest.close, vwap)
    if abs(distance) < 0.05:
        return IndicatorResult("vwap_pressure", DataQualityStatus.OK, 0.0, ("price near VWAP; neutral pressure",))
    direction = 1.0 if distance > 0 else -1.0
    volume_boost = min(1.0, max(0.25, volume_ratio / 2.0))
    score = clamp_score(direction * min(1.0, abs(distance) / 1.0) * volume_boost)
    if score > 0:
        reason = f"price above VWAP by {distance:.2f}% with volume ratio {volume_ratio:.2f}"
    else:
        reason = f"price below VWAP by {abs(distance):.2f}% with volume ratio {volume_ratio:.2f}"
    return IndicatorResult("vwap_pressure", DataQualityStatus.OK, score, (reason,))
