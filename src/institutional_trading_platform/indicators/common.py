"""Shared indicator result contracts for ALPHA-GATE X Phase 3."""

from __future__ import annotations

from dataclasses import dataclass

from ..market_data_spine import DataQualityStatus


@dataclass(frozen=True)
class IndicatorResult:
    """Normalized indicator score with explicit availability and reasons."""

    name: str
    status: DataQualityStatus
    score: float = 0.0
    reasons: tuple[str, ...] = ()

    @property
    def available(self) -> bool:
        """Return whether the indicator has usable real data."""

        return self.status == DataQualityStatus.OK


def clamp_score(value: float) -> float:
    """Clamp an indicator score to the required [-1, +1] range."""

    return max(-1.0, min(1.0, value))


def unavailable(name: str, reason: str) -> IndicatorResult:
    """Build a DATA_UNAVAILABLE indicator result."""

    return IndicatorResult(name=name, status=DataQualityStatus.DATA_UNAVAILABLE, score=0.0, reasons=(reason,))
