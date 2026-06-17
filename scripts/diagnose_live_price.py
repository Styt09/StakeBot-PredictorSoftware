#!/usr/bin/env python3
"""Diagnose why live quote/LTP is not visible.

This script prints only SET/MISSING and sanitized status. It never prints API keys,
access tokens, request tokens, or secrets.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path.cwd()
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from institutional_trading_platform import web_app  # noqa: E402


def mask_status(key: str) -> str:
    value = os.environ.get(key, "").strip()
    return "SET" if value else "MISSING"


def main() -> None:
    print("=== SAFE ENV STATUS ===")
    for key in [
        "ZERODHA_API_KEY",
        "ZERODHA_API_SECRET",
        "ZERODHA_ACCESS_TOKEN",
        "ZERODHA_INSTRUMENT_DUMP_PATH",
    ]:
        print(f"{key}: {mask_status(key)}")

    print("\n=== KITECONNECT LIBRARY ===")
    try:
        import kiteconnect  # type: ignore  # noqa: F401
        print("kiteconnect: INSTALLED")
    except Exception as exc:
        print(f"kiteconnect: MISSING_OR_UNAVAILABLE:{exc.__class__.__name__}")

    print("\n=== CLIENT INIT ===")
    client, reason = web_app._kite_client_from_env()
    print("client:", "READY" if client is not None else "NOT_READY")
    print("reason:", reason)

    print("\n=== QUOTE CHECK ===")
    quote = web_app._market_quote("RELIANCE")
    safe_quote = {
        "symbol": quote.get("symbol"),
        "ltp": quote.get("ltp"),
        "validation_status": quote.get("validation_status"),
        "connection_status": quote.get("connection_status"),
        "data_source": quote.get("data_source"),
        "go_live_allowed": quote.get("go_live_allowed"),
        "message": quote.get("message"),
    }
    print(json.dumps(safe_quote, indent=2))

    print("\n=== VERDICT ===")
    status = safe_quote.get("validation_status")
    ltp = safe_quote.get("ltp")
    reason = str(safe_quote.get("connection_status"))
    if status == "VALIDATED" and isinstance(ltp, (int, float)):
        print("✅ LIVE_PRICE_READY")
    elif reason == "KITECONNECT_LIBRARY_UNAVAILABLE":
        print("❌ INSTALL_KITECONNECT_REQUIRED")
    elif reason == "ZERODHA_CREDENTIALS_UNAVAILABLE":
        print("❌ ZERODHA_API_KEY_OR_ACCESS_TOKEN_MISSING")
    elif "TOKEN" in reason.upper() or "403" in reason or "Permission" in reason:
        print("❌ FRESH_ZERODHA_ACCESS_TOKEN_REQUIRED")
    elif "QUOTE_API_UNAVAILABLE" in reason:
        print("❌ ZERODHA_QUOTE_API_FAILED_OR_TOKEN_EXPIRED")
    else:
        print("❌ DATA_UNAVAILABLE_CHECK_REASON_ABOVE")


if __name__ == "__main__":
    main()
