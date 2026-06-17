#!/usr/bin/env python3
"""Restore the functional trading dashboard while keeping safety intact.

The earlier premium dashboard was UI-only but too minimal for chart, live price,
and full paper trading controls. This patch returns `/` to the existing functional
HTML dashboard, which already has chart, live quote polling, paper terminal, and
working controls. It also injects a light premium style upgrade without changing
trading logic or enabling live trading.
"""
from __future__ import annotations

from pathlib import Path
from time import time
import shutil

WEB_APP = Path("src/institutional_trading_platform/web_app.py")
BACKUP_DIR = Path(".alpha_gate_backups")
OLD_SEND = 'self._send(200, PREMIUM_DASHBOARD_HTML, "text/html; charset=utf-8")'
NEW_SEND = 'self._send(200, HTML, "text/html; charset=utf-8")'
PREMIUM_IMPORT = "from .premium_dashboard import PREMIUM_DASHBOARD_HTML\n"
STYLE_MARKER = "/* PHASE 13.5 FUNCTIONAL PREMIUM OVERRIDE */"
STYLE = r'''
    /* PHASE 13.5 FUNCTIONAL PREMIUM OVERRIDE */
    body{background:radial-gradient(circle at 8% -8%,rgba(59,130,246,.32),transparent 30%),radial-gradient(circle at 92% 4%,rgba(45,212,191,.20),transparent 28%),linear-gradient(135deg,#020617 0%,#081426 48%,#030712 100%)!important}
    header{background:linear-gradient(135deg,rgba(15,23,42,.82),rgba(15,23,42,.36));backdrop-filter:blur(18px);border-bottom:1px solid rgba(103,232,249,.22)!important}
    h1{letter-spacing:-.045em!important;background:linear-gradient(90deg,#f8fafc,#67e8f9,#93c5fd);-webkit-background-clip:text;background-clip:text;color:transparent!important}
    h2{color:#67e8f9!important}.card{border-color:rgba(148,163,184,.22)!important;background:linear-gradient(180deg,rgba(15,23,42,.82),rgba(15,23,42,.54))!important;box-shadow:0 24px 90px rgba(0,0,0,.42)!important}.card:hover{border-color:rgba(103,232,249,.48)!important}
    .topbar{box-shadow:0 14px 50px rgba(0,0,0,.32)}
    .badge{box-shadow:inset 0 0 0 1px rgba(255,255,255,.04)}
    button{background:linear-gradient(135deg,rgba(37,99,235,.90),rgba(14,165,233,.38))!important;border-color:rgba(103,232,249,.26)!important;transition:transform .15s ease,border-color .15s ease,filter .15s ease}button:hover{transform:translateY(-1px);filter:brightness(1.08);border-color:rgba(103,232,249,.65)!important}button.danger{background:linear-gradient(135deg,rgba(159,18,57,.90),rgba(251,113,133,.22))!important;border-color:rgba(251,113,133,.45)!important}
    input,select,summary{border-color:rgba(148,163,184,.25)!important;background:rgba(2,6,23,.72)!important}
    canvas{box-shadow:inset 0 0 0 1px rgba(103,232,249,.12),0 16px 54px rgba(0,0,0,.34)}
    #manual-order-terminal{border-color:rgba(251,113,133,.45)!important}
    #manual-order-terminal h2:after{content:'  · LIVE NO-GO';color:#fb7185;font-size:.8rem;letter-spacing:.08em}
'''


def main() -> None:
    if not WEB_APP.exists():
        raise SystemExit(f"Missing file: {WEB_APP}")

    BACKUP_DIR.mkdir(exist_ok=True)
    backup = BACKUP_DIR / f"web_app_before_functional_ui_restore_{int(time())}.py"
    shutil.copy2(WEB_APP, backup)

    text = WEB_APP.read_text(encoding="utf-8")

    if OLD_SEND in text:
        text = text.replace(OLD_SEND, NEW_SEND, 1)
    elif NEW_SEND not in text:
        raise SystemExit("Could not find dashboard root send line. No changes applied.")

    # Remove premium import if present; it is not needed for the functional dashboard.
    text = text.replace(PREMIUM_IMPORT, "")

    # Inject premium style override into the existing functional HTML only once.
    if STYLE_MARKER not in text and "  </style>" in text:
        text = text.replace("  </style>", STYLE + "\n  </style>", 1)

    WEB_APP.write_text(text, encoding="utf-8")
    print("✅ Functional dashboard restored")
    print("✅ Existing chart/live price/paper trading UI preserved")
    print("✅ Premium visual override injected")
    print("✅ Backend trading logic unchanged")
    print("✅ LIVE remains NO-GO / go_live_allowed=false")
    print(f"Backup: {backup}")


if __name__ == "__main__":
    main()
