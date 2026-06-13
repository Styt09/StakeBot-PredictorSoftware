"""Session clock and intraday square-off helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from enum import StrEnum
from zoneinfo import ZoneInfo


class SessionState(StrEnum):
    PRE_OPEN = "PRE_OPEN"
    MARKET_OPEN = "MARKET_OPEN"
    SQUARE_OFF = "SQUARE_OFF"
    MARKET_CLOSED = "MARKET_CLOSED"


@dataclass(frozen=True)
class SessionManager:
    session_start: time = time(9, 15)
    session_end: time = time(15, 30)
    square_off_time: time = time(15, 15)
    timezone_name: str = "Asia/Kolkata"

    def localize(self, timestamp: datetime) -> datetime:
        if timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        return timestamp.astimezone(ZoneInfo(self.timezone_name))

    def state_at(self, timestamp: datetime) -> SessionState:
        local_time = self.localize(timestamp).time()
        if local_time < self.session_start:
            return SessionState.PRE_OPEN
        if local_time >= self.session_end:
            return SessionState.MARKET_CLOSED
        if local_time >= self.square_off_time:
            return SessionState.SQUARE_OFF
        return SessionState.MARKET_OPEN

    def should_square_off(self, timestamp: datetime) -> bool:
        return self.state_at(timestamp) == SessionState.SQUARE_OFF

    def should_reset_daily_metrics(self, previous: datetime | None, current: datetime) -> bool:
        return previous is not None and self.localize(previous).date() != self.localize(current).date()
