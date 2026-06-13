"""Order-book imbalance scoring for ALPHA-GATE X."""

from __future__ import annotations

from ..market_data_spine import DataQualityStatus, MarketDepth
from .common import IndicatorResult, clamp_score, unavailable


def order_book_imbalance_score(depth: MarketDepth | None, max_spread_percent: float = 0.15) -> IndicatorResult:
    """Score bid/ask pressure from market depth; never fabricates missing depth."""

    if depth is None:
        return unavailable("order_book_imbalance", "market depth unavailable")
    total = depth.bid_quantity + depth.ask_quantity
    if total <= 0:
        return unavailable("order_book_imbalance", "market depth quantity unavailable")
    imbalance = (depth.bid_quantity - depth.ask_quantity) / total
    score = clamp_score(imbalance)
    reason = f"bid quantity {depth.bid_quantity}, ask quantity {depth.ask_quantity}, imbalance {imbalance:.2f}, spread {depth.spread_percent:.2f}%"
    if depth.spread_percent > max_spread_percent:
        return IndicatorResult("order_book_imbalance", DataQualityStatus.OK, score * 0.5, (reason, "abnormal spread reduces confidence"))
    return IndicatorResult("order_book_imbalance", DataQualityStatus.OK, score, (reason,))
