"""Apply Phase 3 market-data safety wiring to local web_app.py.

This additive patch preserves existing dashboard/routes and adds:
- /api/market-data/health
- a small dashboard card for market data health
- optional stale-data helper imports for later phases

It backs up web_app.py before editing.
"""

from __future__ import annotations

from pathlib import Path
import shutil
import time

ROOT = Path(__file__).resolve().parents[1]
WEB_APP = ROOT / "src" / "institutional_trading_platform" / "web_app.py"
BACKUP_DIR = ROOT / ".alpha_gate_backups"

IMPORT_LINE = "from .market_data_safety import ExistingDataProvider, MarketDataHealthService, stale_data_block_payload\n"

CARD_HTML = '''\n<section class="card strong shadow" id="market-data-safety-card">\n  <span class="badge info">MARKET DATA STATUS</span>\n  <span class="badge warn">STALE DATA BLOCKS BUY/SELL</span>\n  <h2>Market Data Safety</h2>\n  <p class="muted">Phase 3 safety layer: quotes/history remain unchanged, but stale or missing data is reported as DATA_UNAVAILABLE for actionable paths.</p>\n  <div id="market-data-health-card" class="kv"></div>\n</section>\n'''

SCRIPT_HOOK = '''\n<script>\nfunction loadMarketDataHealthCard(){\n  const symbolEl=document.getElementById('market-symbol');\n  const symbol=symbolEl?symbolEl.value:'RELIANCE';\n  fetch('/api/market-data/health?symbol='+encodeURIComponent(symbol)).then(r=>r.json()).then(p=>{\n    const el=document.getElementById('market-data-health-card');\n    if(!el)return;\n    el.innerHTML=['state','lastTickTime','dataLatencyMs','dataFreshnessSeconds','marketStatus','validationStatus','go_live_allowed'].map(k=>`<div><strong>${k}</strong>${p[k]}</div>`).join('');\n  }).catch(()=>{});\n}\nsetInterval(loadMarketDataHealthCard,5000);\nloadMarketDataHealthCard();\n</script>\n'''


def main() -> None:
    if not WEB_APP.exists():
        raise SystemExit(f"missing file: {WEB_APP}")
    BACKUP_DIR.mkdir(exist_ok=True)
    backup = BACKUP_DIR / f"web_app_before_phase3_{int(time.time())}.py"
    shutil.copy2(WEB_APP, backup)

    text = WEB_APP.read_text()

    if IMPORT_LINE not in text:
        marker = "from .runtime import InMemoryAuditStore, LivePaperTradingEngine, RuntimeConfig, ShadowRunValidator\n"
        if marker not in text:
            raise SystemExit("import marker not found")
        text = text.replace(marker, marker + IMPORT_LINE, 1)

    if 'path == "/api/market-data/health"' not in text:
        marker = '        elif path == "/api/market/quote":\n            self._send_json(200, _market_quote(_query_symbol(query)))\n'
        insert = marker + '        elif path == "/api/market-data/health":\n            provider = ExistingDataProvider(_market_quote, _market_history)\n            self._send_json(200, MarketDataHealthService(provider).health(_query_symbol(query)))\n'
        if marker not in text:
            raise SystemExit("market quote route marker not found")
        text = text.replace(marker, insert, 1)

    if 'id="market-data-safety-card"' not in text:
        marker = '<section class="card strong shadow" id="live-terminal">'
        if marker not in text:
            raise SystemExit("dashboard insertion marker not found")
        text = text.replace(marker, CARD_HTML + marker, 1)

    if "loadMarketDataHealthCard" not in text:
        marker = "</body></html>"
        if marker not in text:
            raise SystemExit("html body marker not found")
        text = text.replace(marker, SCRIPT_HOOK + marker, 1)

    WEB_APP.write_text(text)
    print(f"PHASE3_MARKET_DATA_SAFETY_PATCHED backup={backup}")


if __name__ == "__main__":
    main()
