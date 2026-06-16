"""Security helpers for redaction and safe error responses."""

from __future__ import annotations

from collections.abc import Mapping

SECRET_MARKERS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "AUTHORIZATION")


def redact_secrets(value: object) -> object:
    """Recursively redact secret-like fields from logs/events/errors."""

    if isinstance(value, Mapping):
        return {str(key): ("<REDACTED>" if any(marker in str(key).upper() for marker in SECRET_MARKERS) else redact_secrets(item)) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_secrets(item) for item in value]
    if isinstance(value, str) and any(marker.lower() in value.lower() for marker in ("api_key", "access_token", "api_secret")):
        return "<REDACTED>"
    return value


def safe_error_response(exc: Exception) -> dict[str, object]:
    return {"error": exc.__class__.__name__, "message": str(redact_secrets(str(exc))), "safe": True}
