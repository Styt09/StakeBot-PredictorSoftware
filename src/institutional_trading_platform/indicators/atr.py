"""ATR indicators and risk ranges for ALPHA-GATE X."""

from __future__ import annotations

from collections.abc import Sequence

from ..market_data_spine import DataQualityStatus, OHLCVCandle
from .common import IndicatorResult, unavailable


def true_ranges(candles: Sequence[OHLCVCandle]) -> tuple[float, ...]:
    """Calculate true range for each completed candle after the first."""

    completed = [candle for candle in candles if candle.complete]
    ranges: list[float] = []
    for previous, current in zip(completed, completed[1:]):
        ranges.append(max(current.high - current.low, abs(current.high - previous.close), abs(current.low - previous.close)))
    return tuple(ranges)


def atr(candles: Sequence[OHLCVCandle], period: int = 14) -> IndicatorResult:
    """Calculate simple ATR with DATA_UNAVAILABLE for insufficient candles."""

    if period <= 0:
        raise ValueError("period must be positive")
    ranges = true_ranges(candles)
    if len(ranges) < period:
        return unavailable("atr", "insufficient completed candles for ATR")
    value = sum(ranges[-period:]) / period
    latest_close = [candle.close for candle in candles if candle.complete][-1]
    atr_percent = (value / latest_close) * 100.0
    return IndicatorResult("atr", DataQualityStatus.OK, value, (f"ATR {value:.4f} ({atr_percent:.2f}% of price)",))


def atr_percent(candles: Sequence[OHLCVCandle], period: int = 14) -> IndicatorResult:
    """Calculate ATR percentage."""

    result = atr(candles, period)
    if not result.available:
        return result
    latest_close = [candle.close for candle in candles if candle.complete][-1]
    percent = (result.score / latest_close) * 100.0
    return IndicatorResult("atr_percent", DataQualityStatus.OK, percent, (f"ATR percentage {percent:.2f}%",))


def atr_stop_loss(entry: float, side: str, atr_value: float, multiplier: float = 1.5) -> float:
    """Return ATR-based stop-loss for BUY or SELL."""

    if entry <= 0 or atr_value <= 0 or multiplier <= 0:
        raise ValueError("entry, ATR, and multiplier must be positive")
    return entry - atr_value * multiplier if side.upper() == "BUY" else entry + atr_value * multiplier


def atr_targets(entry: float, side: str, atr_value: float, first_multiplier: float = 2.0, second_multiplier: float = 3.0) -> tuple[float, float]:
    """Return ATR-based target range."""

    if entry <= 0 or atr_value <= 0:
        raise ValueError("entry and ATR must be positive")
    sign = 1 if side.upper() == "BUY" else -1
    return entry + sign * atr_value * first_multiplier, entry + sign * atr_value * second_multiplier


def expected_move(candles: Sequence[OHLCVCandle], period: int = 14, multiplier: float = 1.0) -> IndicatorResult:
    """Return expected move from ATR."""

    result = atr(candles, period)
    if not result.available:
        return result
    move = result.score * multiplier
    return IndicatorResult("expected_move", DataQualityStatus.OK, move, (f"expected move {move:.4f} from ATR",))
