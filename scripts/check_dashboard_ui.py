#!/usr/bin/env python3
"""Verify that the dashboard is the safe premium UI and does not expose unsafe live trading controls."""
from __future__ import annotations

import sys
import urllib.request

BASE_URL = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://127.0.0.1:8080"
REQUIRED = [
    "LIVE NO-GO",
    "go_live_allowed=false",
    "Paper",
    "Shadow",
    "Kill Switch",
    "Evidence",
    "Broker Read-Only",
]
FORBIDDEN = [
    "Enable Live",
    "Place Real Order",
    "Live Trade Now",
]


def fetch_text(path: str) -> str:
    with urllib.request.urlopen(BASE_URL + path, timeout=8) as response:  # noqa: S310 - local/dev verification script
        return response.read().decode("utf-8", errors="replace")


def main() -> None:
    health = fetch_text("/health")
    html = fetch_text("/")
    missing = [item for item in REQUIRED if item not in html]
    forbidden = [item for item in FORBIDDEN if item in html]

    if "ok" not in health.lower():
        raise SystemExit("❌ /health did not return ok")
    if missing:
        raise SystemExit("❌ Dashboard missing required safe UI text: " + ", ".join(missing))
    if forbidden:
        raise SystemExit("❌ Dashboard contains unsafe live-trading text: " + ", ".join(forbidden))

    print("✅ Dashboard UI verification passed")
    print("✅ LIVE NO-GO visible")
    print("✅ go_live_allowed=false visible")
    print("✅ Paper/Shadow/Evidence/Broker Read-Only sections visible")
    print("✅ No unsafe live-trading buttons detected")


if __name__ == "__main__":
    main()
