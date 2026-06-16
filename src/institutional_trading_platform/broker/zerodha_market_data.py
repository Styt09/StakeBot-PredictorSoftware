"""Zerodha WebSocket tick mapping into ALPHA-GATE X internal ticks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Mapping, Protocol, Sequence

from ..market_data_spine import MarketDepth, Tick
from ..runtime.event_bus import EventBus, RuntimeEvent, RuntimeEventType


@dataclass(frozen=True)
class ZerodhaTickMappingResult:
    tick: Tick | None
    reasons: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.tick is not None and not self.reasons


class ZerodhaWebSocketMarketDataAdapter:
    """Convert Kite ticker payloads to internal ticks; no network connection here."""

    def __init__(self, token_to_symbol: Mapping[int, tuple[str, str]], event_bus: EventBus | None = None) -> None:
        self.token_to_symbol = dict(token_to_symbol)
        self.event_bus = event_bus

    def map_tick(self, payload: Mapping[str, object], received_at: datetime | None = None) -> ZerodhaTickMappingResult:
        reasons: list[str] = []
        received_at = received_at or datetime.now(timezone.utc)
        token = payload.get("instrument_token")
        if not isinstance(token, int) or token not in self.token_to_symbol:
            reasons.append("unknown instrument token")
        price = payload.get("last_price") or payload.get("ltp")
        if not isinstance(price, (int, float)) or price <= 0:
            reasons.append("malformed last_price")
        exchange_timestamp = payload.get("exchange_timestamp") or payload.get("timestamp")
        if not isinstance(exchange_timestamp, datetime) or exchange_timestamp.tzinfo is None:
            reasons.append("missing exchange timestamp")
        if reasons:
            return ZerodhaTickMappingResult(None, tuple(reasons))
        symbol, exchange = self.token_to_symbol[int(token)]
        volume = int(payload.get("volume_traded") or payload.get("volume") or 0)
        depth = self._depth(payload.get("depth"))
        tick = Tick(symbol=symbol, exchange=exchange, timestamp=exchange_timestamp, price=float(price), quantity=max(volume, 0), tick_id=str(payload.get("last_trade_id") or f"{token}-{exchange_timestamp.isoformat()}"), depth=depth)
        if self.event_bus is not None:
            self.event_bus.publish(RuntimeEvent(RuntimeEventType.ZERODHA_TICK_RECEIVED, symbol, {"instrument_token": token, "ltp": float(price), "received_at": received_at.isoformat()}))
        return ZerodhaTickMappingResult(tick)

    @staticmethod
    def _depth(depth_payload: object) -> MarketDepth | None:
        if not isinstance(depth_payload, Mapping):
            return None
        buy = depth_payload.get("buy")
        sell = depth_payload.get("sell")
        if not isinstance(buy, Sequence) or not isinstance(sell, Sequence) or not buy or not sell:
            return None
        best_bid = buy[0]
        best_ask = sell[0]
        if not isinstance(best_bid, Mapping) or not isinstance(best_ask, Mapping):
            return None
        return MarketDepth(float(best_bid.get("price", 0)), int(best_bid.get("quantity", 0)), float(best_ask.get("price", 0)), int(best_ask.get("quantity", 0)))


@dataclass(frozen=True)
class ZerodhaShadowFeedStatus:
    running: bool
    subscribed_tokens: tuple[int, ...]
    malformed_ticks: int
    duplicate_ticks: int
    stale_symbols: tuple[str, ...]
    reconnect_attempts: int
    go_live_allowed: bool = False


class ZerodhaShadowFeedRunner:
    """Read-only Zerodha shadow-feed runner skeleton.

    The runner accepts externally supplied tick payloads; it does not open
    sockets itself and never calls broker order APIs.  Production integration
    should wrap KiteTicker and feed payloads into :meth:`on_payload`.
    """

    def __init__(self, adapter: ZerodhaWebSocketMarketDataAdapter, *, stale_after: timedelta = timedelta(seconds=10), max_reconnect_attempts: int = 5, event_bus: EventBus | None = None) -> None:
        self.adapter = adapter
        self.stale_after = stale_after
        self.max_reconnect_attempts = max_reconnect_attempts
        self.event_bus = event_bus or adapter.event_bus
        self.running = False
        self.subscribed_tokens: set[int] = set()
        self.last_tick_at: dict[str, datetime] = {}
        self.seen_tick_ids: set[str] = set()
        self.malformed_ticks = 0
        self.duplicate_ticks = 0
        self.reconnect_attempts = 0

    def resolve_and_subscribe(self, tokens: Sequence[int]) -> tuple[int, ...]:
        resolved = tuple(token for token in tokens if token in self.adapter.token_to_symbol)
        self.subscribed_tokens.update(resolved)
        return resolved

    def start(self) -> ZerodhaShadowFeedStatus:
        self.running = True
        return self.status()

    def shutdown(self) -> ZerodhaShadowFeedStatus:
        self.running = False
        if self.event_bus is not None:
            self.event_bus.publish(RuntimeEvent(RuntimeEventType.ZERODHA_DISCONNECTED, payload={"reason": "graceful_shutdown"}))
        return self.status()

    def on_payload(self, payload: Mapping[str, object], received_at: datetime | None = None) -> ZerodhaTickMappingResult:
        received_at = received_at or datetime.now(timezone.utc)
        mapped = self.adapter.map_tick(payload, received_at)
        if not mapped.ok:
            self.malformed_ticks += 1
            if self.event_bus is not None:
                self.event_bus.publish(RuntimeEvent(RuntimeEventType.UNSAFE_ACTION_BLOCKED, payload={"reason": "malformed zerodha tick", "details": mapped.reasons}, severity="WARNING", source="zerodha_shadow_feed"))
            return mapped
        tick = mapped.tick
        assert tick is not None
        if tick.tick_id in self.seen_tick_ids:
            self.duplicate_ticks += 1
            if self.event_bus is not None:
                self.event_bus.publish(RuntimeEvent(RuntimeEventType.UNSAFE_ACTION_BLOCKED, tick.symbol, {"reason": "duplicate zerodha tick", "tick_id": tick.tick_id}, severity="WARNING", source="zerodha_shadow_feed"))
            return ZerodhaTickMappingResult(None, ("duplicate tick",))
        self.seen_tick_ids.add(tick.tick_id)
        self.last_tick_at[tick.symbol] = received_at
        return mapped

    def heartbeat(self, now: datetime | None = None) -> ZerodhaShadowFeedStatus:
        now = now or datetime.now(timezone.utc)
        stale = self.stale_symbols(now)
        for symbol in stale:
            if self.event_bus is not None:
                self.event_bus.publish(RuntimeEvent(RuntimeEventType.ALERT_EMITTED, symbol, {"reason": "stale zerodha feed", "stale_after_seconds": self.stale_after.total_seconds()}, severity="CRITICAL", source="zerodha_shadow_feed"))
        return self.status(now)

    def reconnect_backoff_seconds(self) -> int:
        self.reconnect_attempts += 1
        return min(60, 2 ** min(self.reconnect_attempts, self.max_reconnect_attempts))

    def stale_symbols(self, now: datetime | None = None) -> tuple[str, ...]:
        now = now or datetime.now(timezone.utc)
        symbols = {symbol for symbol, _exchange in self.adapter.token_to_symbol.values()}
        return tuple(sorted(symbol for symbol in symbols if symbol not in self.last_tick_at or now - self.last_tick_at[symbol] > self.stale_after))

    def status(self, now: datetime | None = None) -> ZerodhaShadowFeedStatus:
        return ZerodhaShadowFeedStatus(
            running=self.running,
            subscribed_tokens=tuple(sorted(self.subscribed_tokens)),
            malformed_ticks=self.malformed_ticks,
            duplicate_ticks=self.duplicate_ticks,
            stale_symbols=self.stale_symbols(now),
            reconnect_attempts=self.reconnect_attempts,
            go_live_allowed=False,
        )


class ReadOnlyTickerConnection(Protocol):
    """Minimal read-only ticker surface used by the smoke wrapper."""

    on_ticks: Callable[[object, Sequence[Mapping[str, object]]], None] | None
    on_connect: Callable[[object, object], None] | None
    on_close: Callable[[object, int, str], None] | None
    on_error: Callable[[object, int, str], None] | None

    def connect(self, threaded: bool = True) -> None:
        """Open the vendor feed connection."""

    def subscribe(self, tokens: Sequence[int]) -> None:
        """Subscribe to read-only tick updates."""

    def close(self) -> None:
        """Close the vendor feed connection."""


@dataclass(frozen=True)
class ReadOnlyKiteTickerStatus:
    """Read-only KiteTicker smoke status."""

    connected: bool
    subscribed_tokens: tuple[int, ...]
    ticks_seen: int
    malformed_ticks: int
    duplicate_ticks: int
    reconnect_attempts: int
    stale_symbols: tuple[str, ...]
    last_error: str | None = None
    go_live_allowed: bool = False


class ReadOnlyKiteTickerWrapper:
    """Strictly read-only KiteTicker smoke wrapper.

    The wrapper wires a vendor ticker object into :class:`ZerodhaShadowFeedRunner`
    for connection, subscription, heartbeat, reconnect accounting, shutdown, and
    tick validation only.  It exposes no trading, approval, preview, or mutation
    method and never creates signals.
    """

    def __init__(
        self,
        *,
        api_key: str,
        access_token: str,
        token_to_symbol: Mapping[int, tuple[str, str]],
        ticker_factory: Callable[[str, str], ReadOnlyTickerConnection],
        stale_after: timedelta = timedelta(seconds=10),
        event_bus: EventBus | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("ZERODHA_API_KEY missing")
        if not access_token.strip():
            raise ValueError("ZERODHA_ACCESS_TOKEN missing")
        self.event_bus = event_bus
        self.adapter = ZerodhaWebSocketMarketDataAdapter(token_to_symbol, event_bus=event_bus)
        self.runner = ZerodhaShadowFeedRunner(self.adapter, stale_after=stale_after, event_bus=event_bus)
        self.ticker = ticker_factory(api_key, access_token)
        self.connected = False
        self.ticks_seen = 0
        self.last_error: str | None = None
        self.ticker.on_ticks = self._on_ticks
        self.ticker.on_connect = self._on_connect
        self.ticker.on_close = self._on_close
        self.ticker.on_error = self._on_error

    def connect(self) -> ReadOnlyKiteTickerStatus:
        """Connect to the read-only ticker feed."""

        self.ticker.connect(threaded=True)
        return self.status()

    def subscribe(self, tokens: Sequence[int]) -> ReadOnlyKiteTickerStatus:
        """Subscribe only to tokens that can be resolved locally."""

        resolved = self.runner.resolve_and_subscribe(tokens)
        if resolved:
            self.ticker.subscribe(resolved)
        return self.status()

    def heartbeat(self, now: datetime | None = None) -> ReadOnlyKiteTickerStatus:
        """Return heartbeat status and emit stale-feed alerts through the runner."""

        self.runner.heartbeat(now)
        return self.status(now)

    def reconnect_backoff_seconds(self) -> int:
        """Record a reconnect attempt and return bounded exponential backoff."""

        return self.runner.reconnect_backoff_seconds()

    def shutdown(self) -> ReadOnlyKiteTickerStatus:
        """Close the read-only ticker connection."""

        self.ticker.close()
        self.connected = False
        self.runner.shutdown()
        return self.status()

    def _on_connect(self, _ws: object, _response: object) -> None:
        self.connected = True
        self.runner.start()
        if self.event_bus is not None:
            self.event_bus.publish(RuntimeEvent(RuntimeEventType.ZERODHA_CONNECTED, payload={"mode": "read_only_ticker"}))

    def _on_close(self, _ws: object, code: int, reason: str) -> None:
        self.connected = False
        self.runner.shutdown()
        if self.event_bus is not None:
            self.event_bus.publish(RuntimeEvent(RuntimeEventType.ZERODHA_DISCONNECTED, payload={"code": code, "reason": reason}))

    def _on_error(self, _ws: object, code: int, reason: str) -> None:
        self.last_error = f"{code}: {reason}"
        self.connected = False
        self.reconnect_backoff_seconds()
        if self.event_bus is not None:
            self.event_bus.publish(RuntimeEvent(RuntimeEventType.ALERT_EMITTED, payload={"reason": "read-only ticker error", "code": code}, severity="CRITICAL", source="read_only_kite_ticker"))

    def _on_ticks(self, _ws: object, ticks: Sequence[Mapping[str, object]]) -> None:
        for payload in ticks:
            result = self.runner.on_payload(payload)
            if result.ok:
                self.ticks_seen += 1

    def status(self, now: datetime | None = None) -> ReadOnlyKiteTickerStatus:
        runner_status = self.runner.status(now)
        return ReadOnlyKiteTickerStatus(
            connected=self.connected,
            subscribed_tokens=runner_status.subscribed_tokens,
            ticks_seen=self.ticks_seen,
            malformed_ticks=runner_status.malformed_ticks,
            duplicate_ticks=runner_status.duplicate_ticks,
            reconnect_attempts=runner_status.reconnect_attempts,
            stale_symbols=runner_status.stale_symbols,
            last_error=self.last_error,
            go_live_allowed=False,
        )
