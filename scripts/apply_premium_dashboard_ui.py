#!/usr/bin/env python3
"""Apply the Phase 13.5 premium dashboard UI.

This patch is intentionally frontend-only. It keeps the existing HTTP routes and
backend trading safety intact, and changes only the dashboard HTML rendered at `/`.
"""
from __future__ import annotations

from pathlib import Path
from time import time
import shutil

WEB_APP = Path("src/institutional_trading_platform/web_app.py")
BACKUP_DIR = Path(".alpha_gate_backups")
IMPORT_LINE = "from .premium_dashboard import PREMIUM_DASHBOARD_HTML\n"
OLD_ROOT_SEND = 'self._send(200, HTML, "text/html; charset=utf-8")'
NEW_ROOT_SEND = 'self._send(200, PREMIUM_DASHBOARD_HTML, "text/html; charset=utf-8")'


def main() -> None:
    if not WEB_APP.exists():
        raise SystemExit(f"web_app.py not found: {WEB_APP}")

    BACKUP_DIR.mkdir(exist_ok=True)
    backup = BACKUP_DIR / f"web_app_before_premium_dashboard_{int(time())}.py"
    shutil.copy2(WEB_APP, backup)

    text = WEB_APP.read_text(encoding="utf-8")

    if IMPORT_LINE not in text:
        marker = "from .runtime import InMemoryAuditStore, LivePaperTradingEngine, RuntimeConfig, ShadowRunValidator\n"
        if marker in text:
            text = text.replace(marker, marker + IMPORT_LINE, 1)
        else:
            # Safe fallback: add after last local import near the top.
            text = text.replace("DATA_UNAVAILABLE = \"DATA_UNAVAILABLE\"\n", IMPORT_LINE + "\nDATA_UNAVAILABLE = \"DATA_UNAVAILABLE\"\n", 1)

    if NEW_ROOT_SEND not in text:
        if OLD_ROOT_SEND not in text:
            raise SystemExit("Could not find root dashboard send line; no backend logic changed.")
        text = text.replace(OLD_ROOT_SEND, NEW_ROOT_SEND, 1)

    WEB_APP.write_text(text, encoding="utf-8")
    print("✅ Phase 13.5 premium dashboard UI applied")
    print(f"Backup: {backup}")
    print("Safety: backend routes/trading logic untouched; root / now renders PREMIUM_DASHBOARD_HTML")


if __name__ == "__main__":
    main()
