"""Market breadth interface for ALPHA-GATE X."""

from __future__ import annotations

from dataclasses import dataclass

from ..market_data_spine import DataQualityStatus
from .common import IndicatorResult, clamp_score, unavailable


@dataclass(frozen=True)
class MarketBreadthSnapshot:
    """Advance/decline market breadth counts."""

    advancing: int
    declining: int
    unchanged: int = 0

    def validate(self) -> None:
        """Validate breadth counts."""

        if self.advancing < 0 or self.declining < 0 or self.unchanged < 0:
            raise ValueError("breadth counts cannot be negative")

    @property
    def total(self) -> int:
        """Return total symbols in breadth sample."""

        return self.advancing + self.declining + self.unchanged

    @property
    def breadth_ratio(self) -> float:
        """Return advance/decline ratio, with infinity for zero decliners."""

        if self.declining == 0:
            return float("inf") if self.advancing > 0 else 0.0
        return self.advancing / self.declining


def market_breadth_score(snapshot: MarketBreadthSnapshot | None) -> IndicatorResult:
    """Score market breadth from -1 to +1, or DATA_UNAVAILABLE."""

    if snapshot is None:
        return unavailable("market_breadth", "market breadth unavailable")
    try:
        snapshot.validate()
    except ValueError as exc:
        return IndicatorResult("market_breadth", DataQualityStatus.FAIL, 0.0, (str(exc),))
    if snapshot.total == 0:
        return unavailable("market_breadth", "market breadth sample is empty")
    score = clamp_score((snapshot.advancing - snapshot.declining) / snapshot.total)
    return IndicatorResult("market_breadth", DataQualityStatus.OK, score, (f"breadth ratio {snapshot.breadth_ratio:.2f} with {snapshot.advancing} advancing and {snapshot.declining} declining",))
