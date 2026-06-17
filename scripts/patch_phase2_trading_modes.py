"""Apply Phase 2 trading-mode wiring to the local web app safely.

This script preserves the existing dashboard and APIs. It makes a timestamped
backup of web_app.py, then adds:
- /api/config/public
- /api/trading-mode
- startup safe config logging
- a small dashboard warning/banner

It is provided as an opt-in patch because some Codespaces may have local
uncommitted web_app.py changes.
"""

from __future__ import annotations

from pathlib import Path
import shutil
import time

ROOT = Path(__file__).resolve().parents[1]
WEB_APP = ROOT / "src" / "institutional_trading_platform" / "web_app.py"
BACKUP_DIR = ROOT / ".alpha_gate_backups"

IMPORT_LINE = "from .safe_config import getSafePublicConfig, getTradingConfig, startupLogConfig\n"

CARD_HTML = '''\n<section class="card strong shadow" id="trading-mode-safety-card">\n  <span class="badge buy">PAPER MODE</span>\n  <span class="badge danger">LIVE TRADING DISABLED</span>\n  <span class="badge danger">REAL ORDERS BLOCKED</span>\n  <h2>Trading Mode Safety</h2>\n  <p class="muted">Phase 2 safety layer: current mode is served by /api/trading-mode and public config by /api/config/public. Real live order placement remains fail-closed.</p>\n  <div id="trading-mode-card" class="kv"></div>\n</section>\n'''

SCRIPT_HOOK = '''\n<script>\nfetch('/api/trading-mode').then(r=>r.json()).then(p=>{\n  const el=document.getElementById('trading-mode-card');\n  if(!el)return;\n  el.innerHTML=['requestedTradingMode','tradingMode','liveTradingEnabled','brokerConfigured','databaseConfigured','go_live_allowed'].map(k=>`<div><strong>${k}</strong>${p[k]}</div>`).join('');\n}).catch(()=>{});\n</script>\n'''


def main() -> None:
    if not WEB_APP.exists():
        raise SystemExit(f"missing file: {WEB_APP}")

    BACKUP_DIR.mkdir(exist_ok=True)
    backup = BACKUP_DIR / f"web_app_before_phase2_{int(time.time())}.py"
    shutil.copy2(WEB_APP, backup)

    text = WEB_APP.read_text()

    if IMPORT_LINE not in text:
        marker = "from .runtime import InMemoryAuditStore, LivePaperTradingEngine, RuntimeConfig, ShadowRunValidator\n"
        if marker not in text:
            raise SystemExit("import marker not found")
        text = text.replace(marker, marker + IMPORT_LINE, 1)

    if 'path == "/api/config/public"' not in text:
        marker = '        elif path == "/api/status":\n            self._send_json(200, {"active_scope": "live_market_signal_paper_trading", "go_live_allowed": False})\n'
        insert = marker + '        elif path == "/api/config/public":\n            self._send_json(200, getSafePublicConfig())\n        elif path == "/api/trading-mode":\n            config = getTradingConfig()\n            self._send_json(200, {"requestedTradingMode": config.requestedTradingMode, "tradingMode": config.tradingMode.value, "liveTradingEnabled": config.liveTradingEnabled, "brokerConfigured": config.brokerConfigured, "databaseConfigured": config.databaseConfigured, "warnings": config.warnings, "go_live_allowed": False})\n'
        if marker not in text:
            raise SystemExit("/api/status route marker not found")
        text = text.replace(marker, insert, 1)

    if 'id="trading-mode-safety-card"' not in text:
        marker = '<section class="principles">'
        if marker not in text:
            raise SystemExit("dashboard insertion marker not found")
        text = text.replace(marker, CARD_HTML + marker, 1)

    if "fetch('/api/trading-mode')" not in text:
        marker = "</body></html>"
        if marker not in text:
            raise SystemExit("html body marker not found")
        text = text.replace(marker, SCRIPT_HOOK + marker, 1)

    if "startupLogConfig()" not in text:
        marker = 'def run(host: str = "127.0.0.1", port: int = 8080) -> None:\n'
        if marker not in text:
            raise SystemExit("run marker not found")
        text = text.replace(marker, marker + '    print("[ALPHA_GATE_SAFE_CONFIG]", startupLogConfig())\n', 1)

    WEB_APP.write_text(text)
    print(f"PHASE2_TRADING_MODE_PATCHED backup={backup}")


if __name__ == "__main__":
    main()
