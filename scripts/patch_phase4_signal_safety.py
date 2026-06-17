"""Apply Phase 4 safe-signal endpoint wiring to local web_app.py.

This is additive and preserves /api/signal/live. It adds /api/signal/safe and a
small dashboard card without enabling live trading.
"""

from __future__ import annotations

from pathlib import Path
import shutil
import time

ROOT = Path(__file__).resolve().parents[1]
WEB_APP = ROOT / "src" / "institutional_trading_platform" / "web_app.py"
BACKUP_DIR = ROOT / ".alpha_gate_backups"

IMPORT_LINE = "from .signal_safety import safe_signal_from_existing_signal\n"
MD_IMPORT = "from .market_data_safety import ExistingDataProvider, MarketDataHealthService, stale_data_block_payload\n"

CARD_HTML = '''\n<section class="card strong shadow" id="safe-signal-card">\n  <span class="badge info">SAFE SIGNAL FORMAT</span>\n  <span class="badge warn">NO_TRADE WHEN INCOMPLETE</span>\n  <h2>Safe Signal Contract</h2>\n  <p class="muted">Phase 4 adds /api/signal/safe. Existing /api/signal/live remains unchanged. BUY/SELL requires valid data, stop-loss, target, risk-reward, and confidence.</p>\n  <div id="safe-signal-kv" class="kv"></div>\n</section>\n'''

SCRIPT_HOOK = '''\n<script>\nfunction loadSafeSignalCard(){\n  const symbolEl=document.getElementById('market-symbol');\n  const symbol=symbolEl?symbolEl.value:'RELIANCE';\n  fetch('/api/signal/safe?symbol='+encodeURIComponent(symbol)).then(r=>r.json()).then(p=>{\n    const el=document.getElementById('safe-signal-kv');\n    if(!el)return;\n    el.innerHTML=['symbol','action','confidence','confidence_grade','risk_reward','regime','data_quality','go_live_allowed'].map(k=>`<div><strong>${k}</strong>${p[k]}</div>`).join('');\n  }).catch(()=>{});\n}\nsetInterval(loadSafeSignalCard,15000);\nloadSafeSignalCard();\n</script>\n'''


def main() -> None:
    if not WEB_APP.exists():
        raise SystemExit(f"missing file: {WEB_APP}")
    BACKUP_DIR.mkdir(exist_ok=True)
    backup = BACKUP_DIR / f"web_app_before_phase4_{int(time.time())}.py"
    shutil.copy2(WEB_APP, backup)

    text = WEB_APP.read_text()

    if MD_IMPORT not in text:
        marker = "from .runtime import InMemoryAuditStore, LivePaperTradingEngine, RuntimeConfig, ShadowRunValidator\n"
        if marker not in text:
            raise SystemExit("runtime import marker not found")
        text = text.replace(marker, marker + MD_IMPORT, 1)

    if IMPORT_LINE not in text:
        marker = "from .runtime import InMemoryAuditStore, LivePaperTradingEngine, RuntimeConfig, ShadowRunValidator\n"
        if marker in text:
            text = text.replace(marker, marker + IMPORT_LINE, 1)
        elif MD_IMPORT in text:
            text = text.replace(MD_IMPORT, MD_IMPORT + IMPORT_LINE, 1)
        else:
            raise SystemExit("safe signal import marker not found")

    if 'path == "/api/signal/safe"' not in text:
        marker = '        elif path == "/api/signal/live":\n            self._send_json(200, _live_signal(_query_symbol(query), auto_requested=_query_bool(query, "auto_trade")))\n'
        insert = marker + '        elif path == "/api/signal/safe":\n            symbol = _query_symbol(query)\n            provider = ExistingDataProvider(_market_quote, _market_history)\n            health = MarketDataHealthService(provider).health(symbol)\n            signal = _live_signal(symbol, auto_requested=False)\n            self._send_json(200, safe_signal_from_existing_signal(symbol, signal, health))\n'
        if marker not in text:
            raise SystemExit("signal live route marker not found")
        text = text.replace(marker, insert, 1)

    if 'id="safe-signal-card"' not in text:
        marker = '<section class="card strong shadow" id="signal-terminal">'
        if marker not in text:
            raise SystemExit("signal dashboard marker not found")
        text = text.replace(marker, CARD_HTML + marker, 1)

    if "loadSafeSignalCard" not in text:
        marker = "</body></html>"
        if marker not in text:
            raise SystemExit("html body marker not found")
        text = text.replace(marker, SCRIPT_HOOK + marker, 1)

    WEB_APP.write_text(text)
    print(f"PHASE4_SIGNAL_SAFETY_PATCHED backup={backup}")


if __name__ == "__main__":
    main()
