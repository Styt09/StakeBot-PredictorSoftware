"""Market data safety layer for ALPHA-GATE X.

Additive Phase 3 module. It wraps existing quote/history behavior and reports
health without fabricating data or enabling live trading.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time as dt_time
from enum import Enum
from typing import Any, Callable, Mapping, Protocol
from zoneinfo import ZoneInfo

DATA_UNAVAILABLE = "DATA_UNAVAILABLE"


class MarketDataHealthState(str, Enum):
    CONNECTED = "CONNECTED"
    RECONNECTING = "RECONNECTING"
    DISCONNECTED = "DISCONNECTED"
    STALE = "STALE"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"


class MarketDataProvider(Protocol):
    def quote(self, symbol: str) -> Mapping[str, Any]:
        ...

    def history(self, symbol: str, interval: str = "5minute") -> Mapping[str, Any]:
        ...


@dataclass(frozen=True)
class MarketDataHealth:
    symbol: str
    state: MarketDataHealthState
    lastTickTime: str | None
    dataFreshnessSeconds: float | None
    dataLatencyMs: float | None
    missingData: bool
    marketOpen: bool
    marketStatus: str
    dataSource: str
    validationStatus: str
    blockedReasons: tuple[str, ...]
    timestamp: str
    go_live_allowed: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "state": self.state.value,
            "lastTickTime": self.lastTickTime,
            "dataFreshnessSeconds": self.dataFreshnessSeconds,
            "dataLatencyMs": self.dataLatencyMs,
            "missingData": self.missingData,
            "marketOpen": self.marketOpen,
            "marketStatus": self.marketStatus,
            "dataSource": self.dataSource,
            "validationStatus": self.validationStatus,
            "blockedReasons": self.blockedReasons,
            "timestamp": self.timestamp,
            "go_live_allowed": False,
        }


class ExistingDataProvider:
    def __init__(self, quote_fetcher: Callable[[str], Mapping[str, Any]], history_fetcher: Callable[..., Mapping[str, Any]]) -> None:
        self._quote_fetcher = quote_fetcher
        self._history_fetcher = history_fetcher

    def quote(self, symbol: str) -> Mapping[str, Any]:
        normalized = (symbol or "RELIANCE").strip().upper()
        payload = dict(self._quote_fetcher(normalized) or {})
        payload.setdefault("symbol", normalized)
        payload.setdefault("go_live_allowed", False)
        return payload

    def history(self, symbol: str, interval: str = "5minute") -> Mapping[str, Any]:
        normalized = (symbol or "RELIANCE").strip().upper()
        payload = dict(self._history_fetcher(normalized, interval=interval) or {})
        payload.setdefault("symbol", normalized)
        payload.setdefault("interval", interval)
        payload.setdefault("go_live_allowed", False)
        return payload


class MarketDataHealthService:
    def __init__(self, provider: MarketDataProvider, *, timezone: str = "Asia/Kolkata", stale_after_seconds: float = 10.0, reconnecting_after_seconds: float = 30.0) -> None:
        self.provider = provider
        self.timezone = timezone
        self.stale_after_seconds = stale_after_seconds
        self.reconnecting_after_seconds = reconnecting_after_seconds

    def health(self, symbol: str, *, now: datetime | None = None) -> dict[str, Any]:
        normalized = (symbol or "RELIANCE").strip().upper()
        current = _aware_now(now, self.timezone)
        try:
            quote = dict(self.provider.quote(normalized))
        except Exception as exc:
            return MarketDataHealth(normalized, MarketDataHealthState.DISCONNECTED, None, None, None, True, is_market_open(current), market_status(current), DATA_UNAVAILABLE, DATA_UNAVAILABLE, (f"QUOTE_PROVIDER_ERROR:{exc.__class__.__name__}",), current.isoformat()).as_dict()

        last_tick = _parse_time(quote.get("last_update"), self.timezone)
        data_source = str(quote.get("data_source", DATA_UNAVAILABLE))
        validation_status = str(quote.get("validation_status", DATA_UNAVAILABLE))
        ltp = quote.get("ltp")
        missing = validation_status != "VALIDATED" or ltp in (None, "", DATA_UNAVAILABLE)
        freshness = None
        latency_ms = None
        reasons: list[str] = []
        if last_tick is not None:
            freshness = max(0.0, (current - last_tick).total_seconds())
            latency_ms = round(freshness * 1000, 2)
        else:
            reasons.append("LAST_TICK_TIME_UNAVAILABLE")

        if missing:
            reasons.append("QUOTE_DATA_UNAVAILABLE")
            state = MarketDataHealthState.DATA_UNAVAILABLE
        elif freshness is not None and freshness > self.reconnecting_after_seconds:
            reasons.append("MARKET_DATA_RECONNECTING_OR_TOO_OLD")
            state = MarketDataHealthState.RECONNECTING
        elif freshness is not None and freshness > self.stale_after_seconds:
            reasons.append("MARKET_DATA_STALE")
            state = MarketDataHealthState.STALE
        else:
            state = MarketDataHealthState.CONNECTED

        return MarketDataHealth(normalized, state, last_tick.isoformat() if last_tick else None, round(freshness, 3) if freshness is not None else None, latency_ms, missing, is_market_open(current), market_status(current), data_source, validation_status, tuple(dict.fromkeys(reasons)), current.isoformat()).as_dict()


def market_status(now: datetime | None = None, timezone: str = "Asia/Kolkata") -> str:
    return "OPEN" if is_market_open(now, timezone) else "CLOSED"


def is_market_open(now: datetime | None = None, timezone: str = "Asia/Kolkata") -> bool:
    current = _aware_now(now, timezone)
    if current.weekday() >= 5:
        return False
    return dt_time(9, 15) <= current.time() <= dt_time(15, 30)


def is_actionable_data_allowed(health: Mapping[str, Any]) -> bool:
    return health.get("state") == MarketDataHealthState.CONNECTED.value and not bool(health.get("missingData"))


def stale_data_block_payload(symbol: str, health: Mapping[str, Any]) -> dict[str, Any]:
    if is_actionable_data_allowed(health):
        return {"symbol": symbol.strip().upper(), "blocked": False, "go_live_allowed": False}
    return {"symbol": symbol.strip().upper(), "decision": DATA_UNAVAILABLE, "validation_status": DATA_UNAVAILABLE, "data_quality": str(health.get("state", DATA_UNAVAILABLE)), "blocked": True, "blocked_reasons": tuple(health.get("blockedReasons") or ("MARKET_DATA_NOT_ACTIONABLE",)), "go_live_allowed": False}


def _aware_now(now: datetime | None, timezone: str) -> datetime:
    tz = ZoneInfo(timezone)
    if now is None:
        return datetime.now(tz)
    if now.tzinfo is None:
        return now.replace(tzinfo=tz)
    return now.astimezone(tz)


def _parse_time(value: Any, timezone: str) -> datetime | None:
    if value in (None, "", DATA_UNAVAILABLE):
        return None
    if isinstance(value, datetime):
        return _aware_now(value, timezone)
    try:
        return _aware_now(datetime.fromisoformat(str(value).strip().replace("Z", "+00:00")), timezone)
    except ValueError:
        return None
