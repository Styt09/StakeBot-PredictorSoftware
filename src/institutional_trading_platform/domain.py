"""Core domain contracts for institutional trading workflows.

The classes in this module deliberately model only canonical, exchange-agnostic
objects. External vendor or broker adapters should translate their native
payloads into these contracts before downstream research, risk, portfolio, or
execution components consume them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from math import isfinite
from typing import Any


class AssetClass(StrEnum):
    """Supported asset classes for cross-asset research and trading."""

    EQUITY = "equity"
    FUTURE = "future"
    OPTION = "option"
    CURRENCY = "currency"
    COMMODITY = "commodity"
    BOND = "bond"
    ETF = "etf"
    INDEX = "index"


class Venue(StrEnum):
    """Known market venues and data universes."""

    NSE = "NSE"
    BSE = "BSE"
    MCX = "MCX"
    CURRENCY = "CURRENCY"
    GLOBAL = "GLOBAL"


@dataclass(frozen=True)
class Instrument:
    """Canonical security master record used by all platform components."""

    symbol: str
    venue: Venue
    asset_class: AssetClass
    currency: str = "INR"
    lot_size: int = 1
    tick_size: float = 0.01
    isin: str | None = None
    expiry: datetime | None = None
    metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("symbol is required")
        if len(self.currency) != 3 or not self.currency.isalpha():
            raise ValueError("currency must be an ISO-4217 code")
        if self.lot_size <= 0:
            raise ValueError("lot_size must be positive")
        _validate_positive_finite("tick_size", self.tick_size)

    @property
    def instrument_id(self) -> str:
        """Stable platform identifier for the instrument."""

        return f"{self.venue.value}:{self.asset_class.value}:{self.symbol.upper()}"


@dataclass(frozen=True)
class MarketBar:
    """Normalized OHLCV bar for historical and streaming pipelines."""

    instrument: Instrument
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    source: str
    received_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        for field_name in ("open", "high", "low", "close"):
            _validate_positive_finite(field_name, getattr(self, field_name))
        _validate_non_negative_finite("volume", self.volume)
        if self.high < max(self.open, self.close, self.low):
            raise ValueError("high must be greater than or equal to open, low, and close")
        if self.low > min(self.open, self.close, self.high):
            raise ValueError("low must be less than or equal to open, high, and close")
        if not self.source.strip():
            raise ValueError("source is required")
        _require_timezone("timestamp", self.timestamp)
        _require_timezone("received_at", self.received_at)

    def to_feature_row(self) -> dict[str, Any]:
        """Return a deterministic feature-store row for this bar."""

        return {
            "instrument_id": self.instrument.instrument_id,
            "timestamp": self.timestamp.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "source": self.source,
        }


@dataclass(frozen=True)
class OrderBookLevel:
    """Single price level in a level-2 order book snapshot."""

    price: float
    quantity: float
    orders: int = 1

    def __post_init__(self) -> None:
        _validate_positive_finite("price", self.price)
        _validate_non_negative_finite("quantity", self.quantity)
        if self.orders < 0:
            raise ValueError("orders cannot be negative")


@dataclass(frozen=True)
class OrderBookSnapshot:
    """Normalized level-2 order book with validation and microstructure metrics."""

    instrument: Instrument
    timestamp: datetime
    bids: tuple[OrderBookLevel, ...]
    asks: tuple[OrderBookLevel, ...]
    source: str

    def __post_init__(self) -> None:
        if not self.bids or not self.asks:
            raise ValueError("bids and asks are required")
        if not self.source.strip():
            raise ValueError("source is required")
        _require_timezone("timestamp", self.timestamp)
        bid_prices = [level.price for level in self.bids]
        ask_prices = [level.price for level in self.asks]
        if bid_prices != sorted(bid_prices, reverse=True):
            raise ValueError("bids must be sorted by descending price")
        if ask_prices != sorted(ask_prices):
            raise ValueError("asks must be sorted by ascending price")
        if self.best_bid.price >= self.best_ask.price:
            raise ValueError("best bid must be below best ask")

    @property
    def best_bid(self) -> OrderBookLevel:
        """Highest bid level."""

        return self.bids[0]

    @property
    def best_ask(self) -> OrderBookLevel:
        """Lowest ask level."""

        return self.asks[0]

    @property
    def spread(self) -> float:
        """Best ask minus best bid."""

        return self.best_ask.price - self.best_bid.price

    @property
    def mid_price(self) -> float:
        """Top-of-book midpoint."""

        return (self.best_bid.price + self.best_ask.price) / 2.0

    def order_flow_imbalance(self, depth: int | None = None) -> float:
        """Compute normalized bid/ask depth imbalance in [-1, 1]."""

        bid_levels = self.bids[:depth]
        ask_levels = self.asks[:depth]
        bid_quantity = sum(level.quantity for level in bid_levels)
        ask_quantity = sum(level.quantity for level in ask_levels)
        total = bid_quantity + ask_quantity
        if total == 0:
            return 0.0
        return (bid_quantity - ask_quantity) / total


def _validate_positive_finite(name: str, value: float) -> None:
    if not isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be positive and finite")


def _validate_non_negative_finite(name: str, value: float) -> None:
    if not isfinite(value) or value < 0:
        raise ValueError(f"{name} must be non-negative and finite")


def _require_timezone(name: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
