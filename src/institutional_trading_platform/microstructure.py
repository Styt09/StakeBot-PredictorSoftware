"""Microstructure alpha analytics."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from statistics import fmean
from typing import Sequence

from .domain import OrderBookSnapshot


@dataclass(frozen=True)
class FootprintBar:
    """Bid/ask traded volume footprint at one price level."""

    price: float
    bid_volume: float
    ask_volume: float

    def __post_init__(self) -> None:
        if not isfinite(self.price) or self.price <= 0:
            raise ValueError("price must be positive and finite")
        if self.bid_volume < 0 or self.ask_volume < 0:
            raise ValueError("volumes cannot be negative")

    @property
    def delta(self) -> float:
        """Ask volume minus bid volume."""

        return self.ask_volume - self.bid_volume


def order_flow_imbalance(snapshot: OrderBookSnapshot, depth: int | None = None) -> float:
    """Delegate normalized order-flow imbalance to the canonical order book."""

    return snapshot.order_flow_imbalance(depth)


def vpin(buy_volumes: Sequence[float], sell_volumes: Sequence[float], bucket_count: int | None = None) -> float:
    """Volume-synchronized probability of informed trading approximation."""

    if len(buy_volumes) != len(sell_volumes) or not buy_volumes:
        raise ValueError("buy and sell volumes must align and be non-empty")
    if bucket_count is not None and bucket_count <= 0:
        raise ValueError("bucket_count must be positive")
    all_pairs = list(zip(buy_volumes, sell_volumes, strict=True))
    pairs = all_pairs if bucket_count is None else all_pairs[-bucket_count:]
    imbalance = sum(abs(buy - sell) for buy, sell in pairs)
    total = sum(buy + sell for buy, sell in pairs)
    if total == 0:
        return 0.0
    return imbalance / total


def footprint_delta(footprint: Sequence[FootprintBar]) -> float:
    """Aggregate footprint delta."""

    if not footprint:
        raise ValueError("footprint cannot be empty")
    return sum(level.delta for level in footprint)


def liquidity_sweep_score(trade_prices: Sequence[float], trade_sizes: Sequence[float], reference_price: float) -> float:
    """Detect directional liquidity sweeps normalized to [-1, 1]."""

    if len(trade_prices) != len(trade_sizes) or not trade_prices:
        raise ValueError("trade prices and sizes must align and be non-empty")
    if not isfinite(reference_price) or reference_price <= 0:
        raise ValueError("reference_price must be positive and finite")
    signed_volume = 0.0
    total_volume = 0.0
    for price, size in zip(trade_prices, trade_sizes, strict=True):
        if size < 0 or not isfinite(price):
            raise ValueError("trade inputs must be finite and sizes non-negative")
        signed_volume += (1 if price > reference_price else -1 if price < reference_price else 0) * size
        total_volume += size
    return 0.0 if total_volume == 0 else signed_volume / total_volume


def volume_profile(prices: Sequence[float], volumes: Sequence[float], tick_size: float) -> dict[float, float]:
    """Aggregate traded volume by rounded price bucket."""

    if len(prices) != len(volumes) or not prices:
        raise ValueError("prices and volumes must align and be non-empty")
    if tick_size <= 0:
        raise ValueError("tick_size must be positive")
    profile: dict[float, float] = {}
    for price, volume in zip(prices, volumes, strict=True):
        if not isfinite(price) or price <= 0 or volume < 0:
            raise ValueError("prices must be positive finite and volumes non-negative")
        bucket = round(round(price / tick_size) * tick_size, 10)
        profile[bucket] = profile.get(bucket, 0.0) + volume
    return dict(sorted(profile.items()))


def point_of_control(profile: dict[float, float]) -> float:
    """Return price level with maximum volume."""

    if not profile:
        raise ValueError("profile cannot be empty")
    return max(profile.items(), key=lambda item: item[1])[0]


def auction_market_bias(prices: Sequence[float], volumes: Sequence[float]) -> float:
    """Auction market theory bias using close location versus VWAP."""

    if len(prices) != len(volumes) or not prices:
        raise ValueError("prices and volumes must align and be non-empty")
    total_volume = sum(volumes)
    if total_volume <= 0:
        return 0.0
    vwap = sum(price * volume for price, volume in zip(prices, volumes, strict=True)) / total_volume
    price_range = max(prices) - min(prices)
    if price_range == 0:
        return 0.0
    return (prices[-1] - vwap) / price_range


def microprice(snapshot: OrderBookSnapshot) -> float:
    """Top-of-book microprice weighted by displayed quantities."""

    bid = snapshot.best_bid
    ask = snapshot.best_ask
    total = bid.quantity + ask.quantity
    if total == 0:
        return snapshot.mid_price
    return (ask.price * bid.quantity + bid.price * ask.quantity) / total


def average_trade_size(volumes: Sequence[float]) -> float:
    """Validated average trade size helper."""

    if not volumes or any(volume < 0 for volume in volumes):
        raise ValueError("volumes must be non-empty and non-negative")
    return fmean(volumes)
