"""Zerodha instrument mapping placeholder for ALPHA-GATE X.

This module intentionally does not require Zerodha credentials.  Tests and local
configuration can inject a deterministic instrument master exported from a real
provider.  Missing instruments return clear errors instead of dummy tokens.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..market_data_spine import Instrument


class InstrumentMappingError(LookupError):
    """Raised when a requested instrument cannot be mapped safely."""


@dataclass(frozen=True)
class ZerodhaInstrumentRecord:
    """Minimal Zerodha instrument master record."""

    tradingsymbol: str
    exchange: str
    instrument_token: int
    segment: str = "NSE"


class ZerodhaInstrumentMapper:
    """Map symbols to Zerodha instrument tokens for supported exchanges."""

    SUPPORTED_EXCHANGES = {"NSE"}

    def __init__(self, records: tuple[ZerodhaInstrumentRecord, ...] | None = None) -> None:
        self._records = {(record.exchange.upper(), record.tradingsymbol.upper()): record for record in (records or ())}

    def map_symbol(self, symbol: str, exchange: str = "NSE") -> Instrument:
        """Return an instrument mapping or raise a clear lookup error."""

        normalized_exchange = exchange.upper()
        if normalized_exchange not in self.SUPPORTED_EXCHANGES:
            raise InstrumentMappingError(f"exchange {exchange} is not supported yet")
        key = (normalized_exchange, symbol.upper())
        record = self._records.get(key)
        if record is None:
            raise InstrumentMappingError(f"instrument {normalized_exchange}:{symbol} not found in Zerodha instrument master")
        return Instrument(symbol=symbol.upper(), exchange=normalized_exchange, instrument_token=record.instrument_token, tradingsymbol=record.tradingsymbol, segment=record.segment)
