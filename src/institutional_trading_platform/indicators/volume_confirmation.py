"""Volume confirmation indicators for ALPHA-GATE X."""

from __future__ import annotations

from collections.abc import Sequence

from ..market_data_spine import DataQualityStatus, OHLCVCandle
from .common import IndicatorResult, clamp_score, unavailable


def rolling_average_volume(candles: Sequence[OHLCVCandle], period: int = 20) -> float | None:
    """Return rolling average volume for completed candles before the latest."""

    completed = [candle for candle in candles if candle.complete]
    if len(completed) < period + 1:
        return None
    return sum(candle.volume for candle in completed[-period - 1 : -1]) / period


def volume_confirmation_score(candles: Sequence[OHLCVCandle], period: int = 20, low_volume_ratio: float = 0.5) -> IndicatorResult:
    """Score bullish/bearish volume expansion from -1 to +1."""

    completed = [candle for candle in candles if candle.complete]
    average = rolling_average_volume(completed, period)
    if average is None or average <= 0:
        return unavailable("volume_confirmation", "insufficient completed candles for volume average")
    latest = completed[-1]
    ratio = latest.volume / average
    if ratio < low_volume_ratio:
        return IndicatorResult("volume_confirmation", DataQualityStatus.OK, 0.0, (f"low volume warning: ratio {ratio:.2f}",))
    direction = 1.0 if latest.close > latest.open else -1.0 if latest.close < latest.open else 0.0
    score = clamp_score(direction * min(1.0, (ratio - 1.0) / 1.5)) if ratio >= 1 else 0.0
    if score > 0:
        reason = f"bullish volume confirmation with expansion ratio {ratio:.2f}"
    elif score < 0:
        reason = f"bearish volume confirmation with expansion ratio {ratio:.2f}"
    else:
        reason = f"volume neutral with ratio {ratio:.2f}"
    return IndicatorResult("volume_confirmation", DataQualityStatus.OK, score, (reason,))
