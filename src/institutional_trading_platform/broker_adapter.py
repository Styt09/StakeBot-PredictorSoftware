"""Safe broker adapter layer for ALPHA-GATE X.

Phase 8 separates read-only Zerodha operations from mutation operations. Broker
mutation methods are implemented as fail-closed blockers and never call real
place/modify/cancel/exit APIs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter
from typing import Any, Mapping, Protocol

from .safe_config import maskSecret

DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
BROKER = "ZERODHA"


class BrokerAdapter(Protocol):
    def health(self) -> dict[str, Any]: ...
    def quote(self, symbol: str) -> dict[str, Any]: ...
    def profile_status(self) -> dict[str, Any]: ...
    def margins_status(self) -> dict[str, Any]: ...
    def positions_status(self) -> dict[str, Any]: ...
    def place_order(self, payload: Mapping[str, Any]) -> dict[str, Any]: ...
    def modify_order(self, payload: Mapping[str, Any]) -> dict[str, Any]: ...
    def cancel_order(self, payload: Mapping[str, Any]) -> dict[str, Any]: ...
    def exit_position(self, payload: Mapping[str, Any]) -> dict[str, Any]: ...


@dataclass(frozen=True)
class BrokerCredentials:
    api_key: str = ""
    access_token: str = ""
    user_id: str = ""

    @property
    def has_api_key(self) -> bool:
        return bool((self.api_key or "").strip())

    @property
    def has_access_token(self) -> bool:
        return bool((self.access_token or "").strip())

    def masked_user_id(self) -> str | None:
        return maskSecret(self.user_id) if self.user_id else None


class BlockedBrokerMutationAdapter:
    """Fail-closed broker mutation adapter.

    The method names match future broker actions, but these methods return
    BLOCKED and do not call broker APIs.
    """

    def place_order(self, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        return _blocked_mutation("place_order")

    def modify_order(self, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        return _blocked_mutation("modify_order")

    def cancel_order(self, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        return _blocked_mutation("cancel_order")

    def exit_position(self, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        return _blocked_mutation("exit_position")


class ZerodhaReadOnlyAdapter(BlockedBrokerMutationAdapter):
    """Read-only Zerodha adapter around a quote/profile provider.

    Provider methods are dependency-injected so this class is testable and does
    not import KiteConnect directly. The existing web app can pass its existing
    read-only quote helpers.
    """

    def __init__(self, *, credentials: BrokerCredentials, quote_provider: Any | None = None, profile_provider: Any | None = None, margins_provider: Any | None = None, positions_provider: Any | None = None) -> None:
        self.credentials = credentials
        self.quote_provider = quote_provider
        self.profile_provider = profile_provider
        self.margins_provider = margins_provider
        self.positions_provider = positions_provider

    def health(self) -> dict[str, Any]:
        return BrokerHealthService(self).health()

    def quote(self, symbol: str) -> dict[str, Any]:
        if not self.credentials.has_api_key:
            return _safe_readonly_payload("CONFIG_MISSING", symbol=symbol)
        if not self.credentials.has_access_token:
            return _safe_readonly_payload("TOKEN_MISSING", symbol=symbol)
        if self.quote_provider is None:
            return _safe_readonly_payload("BROKER_UNAVAILABLE", symbol=symbol)
        try:
            payload = self.quote_provider(symbol)
            return _sanitize_quote(symbol, payload)
        except Exception as exc:  # pragma: no cover - exact broker errors vary
            return _safe_readonly_payload(_classify_exception(exc), symbol=symbol, error_type=type(exc).__name__)

    def profile_status(self) -> dict[str, Any]:
        return self._read_status(self.profile_provider, "profile")

    def margins_status(self) -> dict[str, Any]:
        return self._read_status(self.margins_provider, "margins")

    def positions_status(self) -> dict[str, Any]:
        return self._read_status(self.positions_provider, "positions")

    def _read_status(self, provider: Any | None, name: str) -> dict[str, Any]:
        if not self.credentials.has_api_key:
            return _safe_readonly_payload("CONFIG_MISSING", endpoint=name)
        if not self.credentials.has_access_token:
            return _safe_readonly_payload("TOKEN_MISSING", endpoint=name)
        if provider is None:
            return _safe_readonly_payload("BROKER_UNAVAILABLE", endpoint=name)
        try:
            result = provider()
            return {
                "status": "CONNECTED",
                "endpoint": name,
                "data": _sanitize_nested(result),
                "read_only": True,
                "mutation_enabled": False,
                "go_live_allowed": False,
            }
        except Exception as exc:  # pragma: no cover - exact broker errors vary
            return _safe_readonly_payload(_classify_exception(exc), endpoint=name, error_type=type(exc).__name__)


class BrokerHealthService:
    def __init__(self, adapter: ZerodhaReadOnlyAdapter) -> None:
        self.adapter = adapter

    def health(self) -> dict[str, Any]:
        start = perf_counter()
        creds = self.adapter.credentials
        status = "CONNECTED"
        connected = False
        latency_ms: float | None = None

        if not creds.has_api_key:
            status = "CONFIG_MISSING"
        elif not creds.has_access_token:
            status = "TOKEN_MISSING"
        else:
            try:
                quote_status = self.adapter.quote("RELIANCE")
                status = str(quote_status.get("status") or "BROKER_UNAVAILABLE")
                connected = status == "CONNECTED"
            except Exception as exc:  # pragma: no cover - defensive fail-closed
                status = _classify_exception(exc)

        latency_ms = round((perf_counter() - start) * 1000, 2)
        return {
            "broker": BROKER,
            "connected": connected,
            "read_only": True,
            "mutation_enabled": False,
            "status": status,
            "latency_ms": latency_ms,
            "last_checked_at": _now(),
            "masked_user_id": creds.masked_user_id(),
            "go_live_allowed": False,
        }


def _blocked_mutation(method: str) -> dict[str, Any]:
    return {
        "status": "BLOCKED",
        "reason": "BROKER_MUTATION_DISABLED",
        "method": method,
        "broker_order_id": None,
        "go_live_allowed": False,
    }


def _safe_readonly_payload(status: str, **extra: Any) -> dict[str, Any]:
    return {
        "broker": BROKER,
        "status": status,
        "read_only": True,
        "mutation_enabled": False,
        **_sanitize_nested(extra),
        "go_live_allowed": False,
    }


def _sanitize_quote(symbol: str, payload: Mapping[str, Any] | None) -> dict[str, Any]:
    raw = dict(payload or {})
    status = raw.get("validation_status") or raw.get("status") or "CONNECTED"
    if status == "VALIDATED":
        status = "CONNECTED"
    ltp = raw.get("ltp") or raw.get("last_price") or raw.get("lastPrice") or DATA_UNAVAILABLE
    return {
        "broker": BROKER,
        "symbol": symbol.upper(),
        "status": status,
        "ltp": ltp,
        "read_only": True,
        "mutation_enabled": False,
        "data": _sanitize_nested(raw),
        "go_live_allowed": False,
    }


def _sanitize_nested(value: Any) -> Any:
    if isinstance(value, Mapping):
        safe: dict[str, Any] = {}
        for key, item in value.items():
            key_str = str(key)
            if _is_secret_key(key_str):
                safe[key_str] = maskSecret(str(item)) if item not in (None, "") else None
            else:
                safe[key_str] = _sanitize_nested(item)
        return safe
    if isinstance(value, (list, tuple)):
        return tuple(_sanitize_nested(item) for item in value)
    return value


def _is_secret_key(key: str) -> bool:
    upper = key.upper()
    return any(token in upper for token in ("SECRET", "TOKEN", "PASSWORD", "API_KEY", "REQUEST_TOKEN", "ACCESS_TOKEN"))


def _classify_exception(exc: Exception) -> str:
    message = str(exc).lower()
    if "token" in message and ("expired" in message or "invalid" in message):
        return "TOKEN_EXPIRED"
    if "token" in message:
        return "BROKER_UNAVAILABLE"
    if "api key" in message or "apikey" in message or "config" in message:
        return "CONFIG_MISSING"
    return "BROKER_UNAVAILABLE"


def _now() -> str:
    return datetime.now(UTC).isoformat()
