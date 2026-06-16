"""Zerodha instrument dump loader and safe token resolver."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from io import StringIO

from ..market_data_spine import Instrument
from ..runtime.event_bus import EventBus, RuntimeEvent, RuntimeEventType


class InstrumentResolutionStatus:
    RESOLVED = "RESOLVED"
    NOT_FOUND = "NOT_FOUND"
    INVALID = "INVALID"


@dataclass(frozen=True)
class ZerodhaInstrument:
    instrument_token: int
    exchange: str
    tradingsymbol: str
    segment: str
    lot_size: int
    tick_size: float


@dataclass(frozen=True)
class InstrumentResolution:
    status: str
    instrument: Instrument | None = None
    zerodha: ZerodhaInstrument | None = None
    reason: str | None = None


class ZerodhaInstrumentManager:
    """Cache a Zerodha instrument dump and resolve symbols safely."""

    SUPPORTED_EXCHANGES = {"NSE"}

    def __init__(self, instruments: tuple[ZerodhaInstrument, ...] = (), event_bus: EventBus | None = None) -> None:
        self._by_key = {(item.exchange.upper(), item.tradingsymbol.upper()): item for item in instruments}
        self.event_bus = event_bus

    @classmethod
    def from_csv(cls, csv_text: str, event_bus: EventBus | None = None) -> "ZerodhaInstrumentManager":
        rows = csv.DictReader(StringIO(csv_text))
        instruments: list[ZerodhaInstrument] = []
        for row in rows:
            instruments.append(
                ZerodhaInstrument(
                    instrument_token=int(row["instrument_token"]),
                    exchange=row.get("exchange", "").upper(),
                    tradingsymbol=row.get("tradingsymbol", "").upper(),
                    segment=row.get("segment", ""),
                    lot_size=int(float(row.get("lot_size", "1") or 1)),
                    tick_size=float(row.get("tick_size", "0.05") or 0.05),
                )
            )
        return cls(tuple(instruments), event_bus=event_bus)

    def resolve(self, symbol: str, exchange: str = "NSE") -> InstrumentResolution:
        normalized_exchange = exchange.upper()
        normalized_symbol = symbol.upper()
        if normalized_exchange not in self.SUPPORTED_EXCHANGES:
            return self._failed(normalized_symbol, normalized_exchange, f"exchange {exchange} unsupported")
        item = self._by_key.get((normalized_exchange, normalized_symbol))
        if item is None:
            return self._failed(normalized_symbol, normalized_exchange, f"instrument {normalized_exchange}:{normalized_symbol} not found")
        if item.lot_size <= 0 or item.tick_size <= 0 or item.segment != normalized_exchange:
            return self._failed(normalized_symbol, normalized_exchange, "invalid Zerodha instrument metadata")
        instrument = Instrument(symbol=normalized_symbol, exchange=normalized_exchange, instrument_token=item.instrument_token, tradingsymbol=item.tradingsymbol, segment=item.segment)
        if self.event_bus is not None:
            self.event_bus.publish(RuntimeEvent(RuntimeEventType.INSTRUMENT_RESOLVED, normalized_symbol, {"instrument_token": item.instrument_token, "lot_size": item.lot_size, "tick_size": item.tick_size}))
        return InstrumentResolution(InstrumentResolutionStatus.RESOLVED, instrument, item)

    def _failed(self, symbol: str, exchange: str, reason: str) -> InstrumentResolution:
        if self.event_bus is not None:
            self.event_bus.publish(RuntimeEvent(RuntimeEventType.INSTRUMENT_RESOLUTION_FAILED, symbol, {"exchange": exchange, "reason": reason}))
        return InstrumentResolution(InstrumentResolutionStatus.NOT_FOUND, reason=reason)
