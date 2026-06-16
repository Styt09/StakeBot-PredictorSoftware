"""Read-only Zerodha integration audit.

This script validates imports, dependency metadata, env readiness, read-only
profile connectivity, instrument resolution, and market-data payload mapping.
It never starts WebSocket shadow trading and never calls order APIs.
"""
from __future__ import annotations

import importlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[0]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(SCRIPT_DIR))

from institutional_trading_platform.broker import ZerodhaInstrumentManager, ZerodhaWebSocketMarketDataAdapter
from institutional_trading_platform.runtime import RuntimeEvent, RuntimeEventType, SQLiteAuditStore
from zerodha_profile_smoke_test import PROFILE_SMOKE_GO, _resolve_dotenv_path, load_env_with_dotenv, run_smoke


def _check_imports() -> dict[str, object]:
    modules = (
        "institutional_trading_platform.broker.zerodha_auth",
        "institutional_trading_platform.broker.zerodha_market_data",
        "institutional_trading_platform.broker.zerodha_instruments",
        "institutional_trading_platform.broker.zerodha_instrument_manager",
    )
    failures: list[str] = []
    for module in modules:
        try:
            importlib.import_module(module)
        except Exception as exc:  # fail closed; report only safe class name/message
            failures.append(f"{module}: {exc.__class__.__name__}: {exc}")
    return {"status": "PASS" if not failures else "FAIL", "modules": modules, "failures": tuple(failures)}


def _check_dependencies() -> dict[str, object]:
    try:
        import pytest  # noqa: F401
        pytest_available = True
    except Exception:
        pytest_available = False
    return {"status": "PASS" if pytest_available else "FAIL", "pytest_available": pytest_available, "install_hint": "pip install -e '.[dev]'" if not pytest_available else ""}


def _check_env(env: Mapping[str, str]) -> dict[str, object]:
    dotenv_path = _resolve_dotenv_path()
    required = ("ZERODHA_API_KEY", "ZERODHA_API_SECRET", "ZERODHA_ACCESS_TOKEN", "AUDIT_DB_PATH")
    missing = tuple(key for key in required if not env.get(key))
    recommended_missing = tuple(key for key in ("ZERODHA_EXPECTED_USER_ID",) if not env.get(key))
    unsafe_flags = {
        key: env.get(key, "").strip().lower()
        for key in ("REAL_ORDER_PLACEMENT_ENABLED", "ENABLE_ZERODHA_WEBSOCKET", "ENABLE_APPROVAL_REQUIRED")
        if env.get(key, "").strip().lower() in {"1", "true", "yes", "on"}
    }
    return {
        "status": "PASS" if not missing and not unsafe_flags else "FAIL",
        "missing": missing,
        "recommended_missing": recommended_missing,
        "unsafe_flags": tuple(sorted(unsafe_flags)),
        "dotenv_found": dotenv_path.exists(),
        "dotenv_path": str(dotenv_path),
        "go_live_allowed": False,
    }


def _check_instruments(env: Mapping[str, str]) -> dict[str, object]:
    path_text = env.get("ZERODHA_INSTRUMENT_DUMP_PATH") or env.get("ZERODHA_INSTRUMENTS_CSV") or ""
    if not path_text:
        return {"status": "DATA_UNAVAILABLE", "reason": "ZERODHA_INSTRUMENT_DUMP_PATH not configured", "go_live_allowed": False}
    path = Path(path_text)
    if not path.exists():
        return {"status": "FAIL", "reason": "instrument dump path not found", "path": str(path), "go_live_allowed": False}
    manager = ZerodhaInstrumentManager.from_csv(path.read_text(encoding="utf-8"))
    symbol = env.get("ZERODHA_AUDIT_SYMBOL", "RELIANCE")
    result = manager.resolve(symbol)
    return {"status": "PASS" if result.instrument is not None else "FAIL", "symbol": symbol, "reason": result.reason, "instrument_token_present": bool(result.instrument and result.instrument.instrument_token), "go_live_allowed": False}


def _check_market_mapping() -> dict[str, object]:
    token = 999999
    timestamp = datetime.now(timezone.utc)
    result = ZerodhaWebSocketMarketDataAdapter({token: ("AUDIT", "NSE")}).map_tick({"instrument_token": token, "last_price": 100.0, "exchange_timestamp": timestamp, "volume_traded": 1})
    malformed = ZerodhaWebSocketMarketDataAdapter({token: ("AUDIT", "NSE")}).map_tick({"instrument_token": token, "last_price": 0})
    return {"status": "PASS" if result.ok and not malformed.ok else "FAIL", "valid_mapping_ok": result.ok, "malformed_rejected": not malformed.ok, "go_live_allowed": False}


class _AuditTicker:
    def __init__(self, api_key: str, access_token: str) -> None:
        self.api_key = api_key
        self.access_token = access_token
        self.on_ticks = None
        self.on_connect = None
        self.on_close = None
        self.on_error = None
        self.subscribed: tuple[int, ...] = ()

    def connect(self, threaded: bool = True) -> None:
        if self.on_connect is not None:
            self.on_connect(self, {"threaded": threaded})

    def subscribe(self, tokens) -> None:
        self.subscribed = tuple(tokens)

    def close(self) -> None:
        if self.on_close is not None:
            self.on_close(self, 1000, "audit_shutdown")


def _check_read_only_ticker_wrapper(env: Mapping[str, str], instrument_report: Mapping[str, object]) -> dict[str, object]:
    if instrument_report.get("status") != "PASS":
        return {"status": "DATA_UNAVAILABLE", "reason": "instrument resolution required before ticker wrapper smoke", "go_live_allowed": False}
    token_present = bool(instrument_report.get("instrument_token_present"))
    if not token_present:
        return {"status": "FAIL", "reason": "instrument token missing", "go_live_allowed": False}
    try:
        market_data = importlib.import_module("institutional_trading_platform.broker.zerodha_market_data")
        wrapper_cls = getattr(market_data, "ReadOnlyKiteTickerWrapper", None)
        if wrapper_cls is None:
            return {"status": "DATA_UNAVAILABLE", "reason": "ReadOnlyKiteTickerWrapper unavailable", "go_live_allowed": False}
        wrapper = wrapper_cls(
            api_key=env.get("ZERODHA_API_KEY", ""),
            access_token=env.get("ZERODHA_ACCESS_TOKEN", ""),
            token_to_symbol={999999: ("AUDIT", "NSE")},
            ticker_factory=_AuditTicker,
        )
        status = wrapper.status()
    except Exception as exc:
        return {"status": "FAIL", "reason": f"{exc.__class__.__name__}: {exc}", "go_live_allowed": False}
    return {"status": "PASS", "connected": status.connected, "subscribed_tokens": status.subscribed_tokens, "go_live_allowed": False}


def run_audit(env: Mapping[str, str] | None = None) -> dict[str, object]:
    env_data = load_env_with_dotenv(env)
    import_report = _check_imports()
    dependency_report = _check_dependencies()
    env_report = _check_env(env_data)
    profile_code, profile_payload = run_smoke(env_data)
    instrument_report = _check_instruments(env_data)
    market_report = _check_market_mapping()
    ticker_wrapper_report = _check_read_only_ticker_wrapper(env_data, instrument_report)
    checks = {
        "imports": import_report,
        "dependencies": dependency_report,
        "environment": env_report,
        "profile_smoke": profile_payload,
        "instruments": instrument_report,
        "market_data_mapping": market_report,
        "read_only_ticker_wrapper": ticker_wrapper_report,
    }
    hard_fail = any(check.get("status") in {"FAIL", "DATA_UNAVAILABLE"} for check in (import_report, dependency_report, env_report, instrument_report, market_report, ticker_wrapper_report)) or profile_payload.get("status") != PROFILE_SMOKE_GO
    report = {"status": "FAIL" if hard_fail else "PASS", "checks": checks, "broker_connection_status": profile_payload.get("status"), "go_live_allowed": False}
    audit_path = env_data.get("AUDIT_DB_PATH", "./alpha_gate_x_audit.db")
    SQLiteAuditStore(audit_path).append(
        RuntimeEvent(
            RuntimeEventType.ZERODHA_INTEGRATION_AUDIT_COMPLETED,
            payload=report,
            source="zerodha_integration_audit",
            severity="CRITICAL" if hard_fail else "INFO",
        )
    )
    return report


def main() -> int:
    report = run_audit()
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
