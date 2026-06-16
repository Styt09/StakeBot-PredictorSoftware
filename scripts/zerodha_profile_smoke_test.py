"""One-shot read-only Zerodha profile/session smoke test.

No WebSocket, no order previews, no order wrappers, and no broker order calls.
"""
from __future__ import annotations

import json
from os import environ
import sys
from pathlib import Path
from typing import Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from institutional_trading_platform.broker import ZerodhaAuthConfig, ZerodhaAuthService, ZerodhaConnectionStatus
from institutional_trading_platform.runtime import RuntimeEvent, RuntimeEventType, SQLiteAuditStore
from institutional_trading_platform.runtime.security import redact_secrets, safe_error_response

PROFILE_SMOKE_GO = "PROFILE_SMOKE_GO"
PROFILE_SMOKE_NO_GO = "PROFILE_SMOKE_NO_GO"

ENV_KEYS = (
    "ZERODHA_API_KEY",
    "ZERODHA_API_SECRET",
    "ZERODHA_ACCESS_TOKEN",
    "ZERODHA_EXPECTED_USER_ID",
    "AUDIT_DB_PATH",
    "ZERODHA_INSTRUMENT_DUMP_PATH",
    "ZERODHA_INSTRUMENTS_CSV",
    "ZERODHA_AUDIT_SYMBOL",
    "REAL_ORDER_PLACEMENT_ENABLED",
    "ENABLE_ZERODHA_WEBSOCKET",
    "ENABLE_APPROVAL_REQUIRED",
)


class ScriptReadOnlyZerodhaProfileClient:
    """Script-local read-only profile client; exposes no mutation methods."""

    PROFILE_URL = "https://api.kite.trade/user/profile"

    def __init__(self, profile_url: str | None = None, timeout_seconds: float = 5.0, opener=None) -> None:
        self.profile_url = profile_url or self.PROFILE_URL
        self.timeout_seconds = timeout_seconds
        self._opener = opener or urlopen

    def profile(self, api_key: str, access_token: str) -> dict[str, object]:
        if not api_key:
            raise RuntimeError("ZERODHA_API_KEY missing")
        if not access_token:
            raise RuntimeError("ZERODHA_ACCESS_TOKEN missing")
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
            raise RuntimeError(f"profile endpoint auth/network failure: HTTP {exc.code}") from exc
        except URLError as exc:
            safe = safe_error_response(exc)
            raise RuntimeError(f"profile endpoint unreachable: {safe['message']}") from exc
        except Exception as exc:
            safe = safe_error_response(exc)
            raise RuntimeError(f"profile endpoint failed: {safe['message']}") from exc
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError("profile endpoint returned malformed JSON") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("profile endpoint returned non-object JSON")
        if payload.get("status") not in {None, "success"}:
            message = str(payload.get("message") or "profile endpoint returned non-success status")
            raise RuntimeError(str(safe_error_response(RuntimeError(message))["message"]))
        data = payload.get("data", payload)
        if not isinstance(data, dict):
            raise RuntimeError("profile response missing data object")
        return data


def _redact_value(value: str) -> str:
    value = value.strip()
    if not value:
        return "<MISSING>"
    if len(value) <= 6:
        return "<REDACTED>"
    return f"{value[:2]}...{value[-2:]}"


def _resolve_dotenv_path(dotenv_path: str | Path = ".env", env: Mapping[str, str] | None = None) -> Path:
    source = environ if env is None else env
    configured = source.get("ZERODHA_ENV_PATH", "").strip()
    candidates = [Path(configured)] if configured else []
    requested = Path(dotenv_path)
    candidates.append(requested)
    script_root = Path(__file__).resolve().parents[1]
    repo_root = script_root
    for base in (Path.cwd(), repo_root, repo_root.parent, Path.home()):
        candidates.extend((base / ".env", base / ".env.local", base / "config" / ".env", base / "config" / "zerodha.env"))
    seen: set[Path] = set()
    for candidate in candidates:
        if not candidate:
            continue
        expanded = candidate.expanduser()
        if expanded in seen:
            continue
        seen.add(expanded)
        if expanded.exists():
            return expanded
    return requested


def load_env_with_dotenv(env: Mapping[str, str] | None = None, dotenv_path: str | Path = ".env") -> dict[str, str]:
    """Load required env vars, using shell values, ZERODHA_ENV_PATH, or repo-local .env."""

    source = dict(environ if env is None else env)
    path = _resolve_dotenv_path(dotenv_path, source)
    if path.exists():
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip().removeprefix("export ").strip().lstrip("\ufeff")
            if key in ENV_KEYS and not source.get(key):
                source[key] = value.strip().strip('"').strip("'")
    return source


def _env_diagnostics(env: Mapping[str, str]) -> dict[str, object]:
    dotenv_path = _resolve_dotenv_path(env=env)
    return {
        "dotenv_path": str(dotenv_path),
        "dotenv_found": dotenv_path.exists(),
        "ZERODHA_API_KEY": _redact_value(env.get("ZERODHA_API_KEY", "")),
        "ZERODHA_API_SECRET": _redact_value(env.get("ZERODHA_API_SECRET", "")),
        "ZERODHA_ACCESS_TOKEN": _redact_value(env.get("ZERODHA_ACCESS_TOKEN", "")),
        "ZERODHA_EXPECTED_USER_ID": env.get("ZERODHA_EXPECTED_USER_ID", "") or "<MISSING>",
        "AUDIT_DB_PATH": env.get("AUDIT_DB_PATH", "") or "<MISSING>",
        "ZERODHA_INSTRUMENT_DUMP_PATH": env.get("ZERODHA_INSTRUMENT_DUMP_PATH", "") or env.get("ZERODHA_INSTRUMENTS_CSV", "") or "<MISSING>",
        "REAL_ORDER_PLACEMENT_ENABLED": env.get("REAL_ORDER_PLACEMENT_ENABLED", "false") or "false",
        "ENABLE_ZERODHA_WEBSOCKET": env.get("ENABLE_ZERODHA_WEBSOCKET", "false") or "false",
        "ENABLE_APPROVAL_REQUIRED": env.get("ENABLE_APPROVAL_REQUIRED", "false") or "false",
    }


def _payload(status: str, reasons: tuple[str, ...], *, user_id: str | None, profile_reachable: bool, env: Mapping[str, str]) -> dict[str, object]:
    safe_reasons = tuple(str(redact_secrets({"message": reason})["message"]) for reason in reasons)
    return {
        "status": status,
        "reasons": safe_reasons,
        "user_id": user_id,
        "profile_reachable": profile_reachable,
        "api_key_present": bool(env.get("ZERODHA_API_KEY", "").strip()),
        "api_secret_present": bool(env.get("ZERODHA_API_SECRET", "").strip()),
        "access_token_present": bool(env.get("ZERODHA_ACCESS_TOKEN", "").strip()),
        "expected_user_id_present": bool(env.get("ZERODHA_EXPECTED_USER_ID", "").strip()),
        "env_diagnostics": _env_diagnostics(env),
        "go_live_allowed": False,
    }


def run_smoke(env: Mapping[str, str] | None = None, profile_client: object | None = None) -> tuple[int, dict[str, object]]:
    env = load_env_with_dotenv(env)
    config = ZerodhaAuthConfig(
        api_key=env.get("ZERODHA_API_KEY", "").strip(),
        access_token=env.get("ZERODHA_ACCESS_TOKEN", "").strip(),
        expected_user_id=env.get("ZERODHA_EXPECTED_USER_ID", "").strip(),
    )
    audit_path = env.get("AUDIT_DB_PATH", "./alpha_gate_x_audit.db")
    store = SQLiteAuditStore(audit_path)
    client = profile_client or ScriptReadOnlyZerodhaProfileClient()
    state = ZerodhaAuthService(config, profile_client=client).validate()
    ok = state.status == ZerodhaConnectionStatus.CONNECTED and state.profile_reachable and not state.reasons
    event_type = RuntimeEventType.ZERODHA_READ_ONLY_PROFILE_SMOKE_PASSED if ok else RuntimeEventType.ZERODHA_READ_ONLY_PROFILE_SMOKE_FAILED
    output_status = PROFILE_SMOKE_GO if ok else PROFILE_SMOKE_NO_GO
    payload = _payload(output_status, state.reasons, user_id=state.user_id, profile_reachable=state.profile_reachable, env=env)
    store.append(RuntimeEvent(event_type, payload=payload, source="zerodha_profile_smoke", severity="INFO" if ok else "CRITICAL"))
    return (0 if ok else 2), {"status": output_status, **payload}


def main() -> int:
    code, payload = run_smoke()
    print(payload)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
