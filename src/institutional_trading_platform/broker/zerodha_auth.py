"""Safe Zerodha auth configuration for Phase 6.

No credentials are hardcoded here.  Missing credentials are represented as a
safe unavailable state rather than triggering any live broker action.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import json
from os import environ
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..runtime.event_bus import EventBus, RuntimeEvent, RuntimeEventType
from ..runtime.security import safe_error_response


class ZerodhaConnectionStatus(StrEnum):
    CONNECTED = "CONNECTED"
    ZERODHA_UNAVAILABLE = "ZERODHA_UNAVAILABLE"
    AUTH_FAILED = "AUTH_FAILED"


@dataclass(frozen=True)
class ZerodhaAuthConfig:
    api_key: str
    access_token: str
    redirect_url: str = "http://localhost:8000/auth/zerodha/callback"
    expected_user_id: str = ""

    @classmethod
    def from_env(cls) -> "ZerodhaAuthConfig":
        return cls(
            api_key=environ.get("ZERODHA_API_KEY", "").strip(),
            access_token=environ.get("ZERODHA_ACCESS_TOKEN", "").strip(),
            redirect_url=environ.get("ZERODHA_REDIRECT_URL", "http://localhost:8000/auth/zerodha/callback").strip(),
            expected_user_id=environ.get("ZERODHA_EXPECTED_USER_ID", "").strip(),
        )

    @property
    def is_available(self) -> bool:
        return bool(self.api_key and self.access_token)


@dataclass(frozen=True)
class ZerodhaAuthState:
    status: ZerodhaConnectionStatus
    reasons: tuple[str, ...] = ()
    user_id: str | None = None
    profile_reachable: bool = False
    go_live_allowed: bool = False


class ZerodhaProfileClient(Protocol):
    """Read-only profile client abstraction; must never expose order APIs."""

    def profile(self, api_key: str, access_token: str) -> dict[str, object]:
        """Return a read-only Zerodha profile payload or raise on auth/network failure."""


class ZerodhaProfileClientError(RuntimeError):
    """Fail-closed read-only profile validation error with redacted details."""


class RealZerodhaProfileClient:
    """Concrete read-only Zerodha profile client.

    This client calls only the Kite Connect profile endpoint.  It deliberately
    exposes no order, order-preview, WebSocket, or mutation methods.
    """

    PROFILE_URL = "https://api.kite.trade/user/profile"

    def __init__(self, profile_url: str | None = None, timeout_seconds: float = 5.0, opener=None) -> None:
        self.profile_url = profile_url or self.PROFILE_URL
        self.timeout_seconds = timeout_seconds
        self._opener = opener or urlopen

    def profile(self, api_key: str, access_token: str) -> dict[str, object]:
        if not api_key:
            raise ZerodhaProfileClientError("ZERODHA_API_KEY missing")
        if not access_token:
            raise ZerodhaProfileClientError("ZERODHA_ACCESS_TOKEN missing")
        request = Request(
            self.profile_url,
            headers={
                "Authorization": f"token {api_key}:{access_token}",
                "X-Kite-Version": "3",
                "Accept": "application/json",
            },
            method="GET",
        )
        try:
            with self._opener(request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            raise ZerodhaProfileClientError(f"profile endpoint auth/network failure: HTTP {exc.code}") from exc
        except URLError as exc:
            safe = safe_error_response(exc)
            raise ZerodhaProfileClientError(f"profile endpoint unreachable: {safe['message']}") from exc
        except Exception as exc:
            safe = safe_error_response(exc)
            raise ZerodhaProfileClientError(f"profile endpoint failed: {safe['message']}") from exc
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ZerodhaProfileClientError("profile endpoint returned malformed JSON") from exc
        if not isinstance(payload, dict):
            raise ZerodhaProfileClientError("profile endpoint returned non-object JSON")
        if payload.get("status") not in {None, "success"}:
            message = str(payload.get("message") or "profile endpoint returned non-success status")
            raise ZerodhaProfileClientError(str(safe_error_response(RuntimeError(message))["message"]))
        data = payload.get("data", payload)
        if not isinstance(data, dict):
            raise ZerodhaProfileClientError("profile response missing data object")
        return data


class ZerodhaAuthService:
    """Validate Zerodha credentials through a read-only profile check."""

    def __init__(self, config: ZerodhaAuthConfig | None = None, event_bus: EventBus | None = None, profile_client: ZerodhaProfileClient | None = None) -> None:
        self.config = config or ZerodhaAuthConfig.from_env()
        self.event_bus = event_bus
        self.profile_client = profile_client

    def validate(self) -> ZerodhaAuthState:
        reasons: list[str] = []
        if not self.config.api_key:
            reasons.append("ZERODHA_API_KEY missing")
        if not self.config.access_token:
            reasons.append("ZERODHA_ACCESS_TOKEN missing")
        if self.profile_client is None:
            reasons.append("Zerodha read-only profile client unavailable")
        if reasons:
            state = ZerodhaAuthState(ZerodhaConnectionStatus.ZERODHA_UNAVAILABLE, tuple(reasons), profile_reachable=False)
            if self.event_bus is not None:
                self.event_bus.publish(RuntimeEvent(RuntimeEventType.ZERODHA_AUTH_FAILED, payload={"reasons": state.reasons}))
            return state
        try:
            profile = self.profile_client.profile(self.config.api_key, self.config.access_token)
        except Exception as exc:  # read-only auth failure must fail closed
            state = ZerodhaAuthState(ZerodhaConnectionStatus.ZERODHA_UNAVAILABLE, (f"profile check failed: {exc}",), profile_reachable=False)
            if self.event_bus is not None:
                self.event_bus.publish(RuntimeEvent(RuntimeEventType.ZERODHA_AUTH_FAILED, payload={"reasons": state.reasons}))
            return state
        user_id = str(profile.get("user_id") or profile.get("userId") or "")
        if not user_id:
            state = ZerodhaAuthState(ZerodhaConnectionStatus.ZERODHA_UNAVAILABLE, ("profile missing user_id",), profile_reachable=True)
            if self.event_bus is not None:
                self.event_bus.publish(RuntimeEvent(RuntimeEventType.ZERODHA_AUTH_FAILED, payload={"reasons": state.reasons}))
            return state
        if bool(profile.get("revoked") or profile.get("session_revoked")):
            state = ZerodhaAuthState(ZerodhaConnectionStatus.ZERODHA_UNAVAILABLE, ("Zerodha session revoked",), user_id=user_id, profile_reachable=True)
            if self.event_bus is not None:
                self.event_bus.publish(RuntimeEvent(RuntimeEventType.ZERODHA_AUTH_FAILED, payload={"reasons": state.reasons, "user_id": user_id}))
            return state
        if self.config.expected_user_id and user_id != self.config.expected_user_id:
            state = ZerodhaAuthState(ZerodhaConnectionStatus.ZERODHA_UNAVAILABLE, ("Zerodha user mismatch",), user_id=user_id, profile_reachable=True)
            if self.event_bus is not None:
                self.event_bus.publish(RuntimeEvent(RuntimeEventType.ZERODHA_AUTH_FAILED, payload={"reasons": state.reasons, "user_id": user_id}))
            return state
        state = ZerodhaAuthState(ZerodhaConnectionStatus.CONNECTED, (), user_id=user_id, profile_reachable=True)
        if self.event_bus is not None:
            self.event_bus.publish(RuntimeEvent(RuntimeEventType.ZERODHA_CONNECTED, payload={"api_key_present": True, "profile_reachable": True, "user_id": user_id}))
        return state
