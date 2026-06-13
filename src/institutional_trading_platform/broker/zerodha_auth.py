"""Safe Zerodha auth configuration for Phase 6.

No credentials are hardcoded here.  Missing credentials are represented as a
safe unavailable state rather than triggering any live broker action.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from os import environ

from ..runtime.event_bus import EventBus, RuntimeEvent, RuntimeEventType


class ZerodhaConnectionStatus(StrEnum):
    CONNECTED = "CONNECTED"
    ZERODHA_UNAVAILABLE = "ZERODHA_UNAVAILABLE"
    AUTH_FAILED = "AUTH_FAILED"


@dataclass(frozen=True)
class ZerodhaAuthConfig:
    api_key: str
    access_token: str
    redirect_url: str = "http://localhost:8000/auth/zerodha/callback"

    @classmethod
    def from_env(cls) -> "ZerodhaAuthConfig":
        return cls(
            api_key=environ.get("ZERODHA_API_KEY", "").strip(),
            access_token=environ.get("ZERODHA_ACCESS_TOKEN", "").strip(),
            redirect_url=environ.get("ZERODHA_REDIRECT_URL", "http://localhost:8000/auth/zerodha/callback").strip(),
        )

    @property
    def is_available(self) -> bool:
        return bool(self.api_key and self.access_token)


@dataclass(frozen=True)
class ZerodhaAuthState:
    status: ZerodhaConnectionStatus
    reasons: tuple[str, ...] = ()


class ZerodhaAuthService:
    """Validate env-provided Zerodha credentials without placing orders."""

    def __init__(self, config: ZerodhaAuthConfig | None = None, event_bus: EventBus | None = None) -> None:
        self.config = config or ZerodhaAuthConfig.from_env()
        self.event_bus = event_bus

    def validate(self) -> ZerodhaAuthState:
        reasons: list[str] = []
        if not self.config.api_key:
            reasons.append("ZERODHA_API_KEY missing")
        if not self.config.access_token:
            reasons.append("ZERODHA_ACCESS_TOKEN missing")
        if reasons:
            state = ZerodhaAuthState(ZerodhaConnectionStatus.ZERODHA_UNAVAILABLE, tuple(reasons))
            if self.event_bus is not None:
                self.event_bus.publish(RuntimeEvent(RuntimeEventType.ZERODHA_AUTH_FAILED, payload={"reasons": state.reasons}))
            return state
        state = ZerodhaAuthState(ZerodhaConnectionStatus.CONNECTED, ())
        if self.event_bus is not None:
            self.event_bus.publish(RuntimeEvent(RuntimeEventType.ZERODHA_CONNECTED, payload={"api_key_present": True}))
        return state
