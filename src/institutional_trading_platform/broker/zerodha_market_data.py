"""Zerodha WebSocket tick mapping into ALPHA-GATE X internal ticks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping, Sequence

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
