"""Trend-regime detection for ALPHA-GATE X."""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum

from ..market_data_spine import DataQualityStatus, OHLCVCandle
from .atr import atr_percent
from .common import IndicatorResult, clamp_score, unavailable


class TrendRegimeLabel(StrEnum):
    """Supported deterministic trend regimes."""

    BULLISH_TREND = "BULLISH_TREND"
    BEARISH_TREND = "BEARISH_TREND"
    RANGE = "RANGE"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    DANGER = "DANGER"
    UNKNOWN = "UNKNOWN"


def ema(values: Sequence[float], period: int) -> float | None:
    """Calculate EMA for a completed value sequence."""

    if period <= 0:
        raise ValueError("period must be positive")
    if len(values) < period:
        return None
    alpha = 2 / (period + 1)
    value = sum(values[:period]) / period
    for price in values[period:]:
        value = alpha * price + (1 - alpha) * value
    return value


def trend_regime(candles: Sequence[OHLCVCandle], atr_period: int = 14, danger_atr_percent: float = 8.0) -> IndicatorResult:
    """Detect trend regime using EMA 20/50, slope, volatility, and structure."""

    completed = [candle for candle in candles if candle.complete]
    if len(completed) < 50:
        return unavailable("trend_regime", "insufficient completed candles for EMA20/EMA50 regime")
    closes = [candle.close for candle in completed]
    ema20 = ema(closes, 20)
    ema50 = ema(closes, 50)
    previous_ema20 = ema(closes[:-1], 20)
    atrp = atr_percent(completed, atr_period)
    if ema20 is None or ema50 is None or previous_ema20 is None or not atrp.available:
        return unavailable("trend_regime", "trend regime inputs unavailable")
    if atrp.score >= danger_atr_percent:
        return IndicatorResult("trend_regime", DataQualityStatus.OK, -1.0, (TrendRegimeLabel.DANGER.value, f"ATR percentage {atrp.score:.2f}% exceeds danger threshold"))
    slope = ema20 - previous_ema20
    higher_high = completed[-1].high > completed[-2].high
    higher_low = completed[-1].low > completed[-2].low
    lower_high = completed[-1].high < completed[-2].high
    lower_low = completed[-1].low < completed[-2].low
    separation = abs(ema20 - ema50) / closes[-1]
    if ema20 > ema50 and slope > 0 and higher_high and higher_low:
        score = clamp_score(0.55 + min(0.35, separation * 20))
        return IndicatorResult("trend_regime", DataQualityStatus.OK, score, (TrendRegimeLabel.BULLISH_TREND.value, "EMA20 above EMA50 with positive slope and bullish candle structure"))
    if ema20 < ema50 and slope < 0 and lower_high and lower_low:
        score = clamp_score(-0.55 - min(0.35, separation * 20))
        return IndicatorResult("trend_regime", DataQualityStatus.OK, score, (TrendRegimeLabel.BEARISH_TREND.value, "EMA20 below EMA50 with negative slope and bearish candle structure"))
    if atrp.score >= danger_atr_percent / 2:
        return IndicatorResult("trend_regime", DataQualityStatus.OK, 0.0, (TrendRegimeLabel.HIGH_VOLATILITY.value, f"ATR percentage {atrp.score:.2f}% elevated"))
    return IndicatorResult("trend_regime", DataQualityStatus.OK, 0.0, (TrendRegimeLabel.RANGE.value, "EMA alignment or candle structure lacks trend confirmation"))
