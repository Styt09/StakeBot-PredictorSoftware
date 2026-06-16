"""Liquidity sweep detection for ALPHA-GATE X."""

from __future__ import annotations

from collections.abc import Sequence

from ..market_data_spine import DataQualityStatus, OHLCVCandle
from .common import IndicatorResult, unavailable


def liquidity_sweep_score(candles: Sequence[OHLCVCandle], lookback: int = 5) -> IndicatorResult:
    """Detect previous high/low sweeps and reclaim/failure patterns."""

    completed = [candle for candle in candles if candle.complete]
    if len(completed) < lookback + 1:
        return unavailable("liquidity_sweep", "insufficient completed candles for liquidity sweep")
    latest = completed[-1]
    previous = completed[-lookback - 1 : -1]
    previous_high = max(candle.high for candle in previous)
    previous_low = min(candle.low for candle in previous)
    if latest.low < previous_low and latest.close > previous_low:
        return IndicatorResult("liquidity_sweep", DataQualityStatus.OK, 0.8, ("bullish previous low sweep and reclaim",))
    if latest.high > previous_high and latest.close < previous_high:
        return IndicatorResult("liquidity_sweep", DataQualityStatus.OK, -0.8, ("bearish previous high sweep and rejection",))
    if latest.high > previous_high and latest.close <= latest.open:
        return IndicatorResult("liquidity_sweep", DataQualityStatus.OK, -0.5, ("failed breakout after previous high sweep",))
    if latest.low < previous_low and latest.close >= latest.open:
        return IndicatorResult("liquidity_sweep", DataQualityStatus.OK, 0.5, ("failed breakdown after previous low sweep",))
    return IndicatorResult("liquidity_sweep", DataQualityStatus.OK, 0.0, ("no liquidity sweep detected",))
