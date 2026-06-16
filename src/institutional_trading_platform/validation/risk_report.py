"""Risk-block reporting for ALPHA-GATE X validation."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class RiskEventRecord:
    """Validation-time risk event."""

    reason: str
    severity: str = "BLOCK"


@dataclass(frozen=True)
class RiskReport:
    daily_loss_limit_breaches: int
    max_trades_per_day_breaches: int
    max_open_position_breaches: int
    kill_switch_activations: int
    risk_block_reasons: dict[str, int]
    bad_data_block_count: int
    stale_data_block_count: int
    data_unavailable_count: int
    rejected_signal_count: int


def build_risk_report(events: Sequence[RiskEventRecord]) -> RiskReport:
    """Summarize risk blocks and rejected signals."""

    reasons = Counter(event.reason for event in events)
    return RiskReport(
        daily_loss_limit_breaches=reasons.get("daily loss limit hit", 0),
        max_trades_per_day_breaches=reasons.get("max trades per day hit", 0),
        max_open_position_breaches=reasons.get("max open positions hit", 0),
        kill_switch_activations=reasons.get("kill switch active", 0),
        risk_block_reasons=dict(reasons),
        bad_data_block_count=sum(count for reason, count in reasons.items() if "bad data" in reason or "data quality" in reason),
        stale_data_block_count=reasons.get("stale data", 0),
        data_unavailable_count=sum(count for reason, count in reasons.items() if "DATA_UNAVAILABLE" in reason or "unavailable" in reason),
        rejected_signal_count=len(events),
    )
