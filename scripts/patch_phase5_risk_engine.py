from __future__ import annotations

from pathlib import Path
import shutil
import time

ROOT = Path(__file__).resolve().parents[1]
WEB_APP = ROOT / "src" / "institutional_trading_platform" / "web_app.py"
BACKUP = ROOT / ".alpha_gate_backups"

IMPORTS = (
    "from .risk_engine import RiskEngine, RiskInput\n"
    "from .market_data_safety import ExistingDataProvider, MarketDataHealthService\n"
    "from .signal_safety import safe_signal_from_existing_signal\n"
)

HELPER = '''

def _risk_check_for_symbol(symbol: str, quantity: int = 1, side: str = "BUY") -> dict[str, Any]:
    provider = ExistingDataProvider(_market_quote, _market_history)
    health = MarketDataHealthService(provider).health(symbol)
    raw_signal = _live_signal(symbol, auto_requested=False)
    safe_signal = safe_signal_from_existing_signal(symbol, raw_signal, health)
    return RiskEngine().evaluate(RiskInput(
        symbol=symbol,
        side=side,
        quantity=quantity,
        signal=safe_signal,
        market_health=health,
        account_state=_paper_status().get("account_summary", {}),
        open_positions=tuple(_PAPER.get("open_positions", ())),
        order_path="PAPER",
        kill_switch_active=_kill_switch_active(),
    ))
'''

CARD = '''
<section class="card strong shadow" id="risk-engine-card"><span class="badge danger">RISK ENGINE</span><span class="badge warn">ORDERS REQUIRE RISK APPROVAL</span><h2>Risk Engine Status</h2><p class="muted">Central risk checks are now evaluated before paper order routing. Real order paths remain blocked.</p><div id="risk-engine-kv" class="kv"></div></section>
'''

SCRIPT = '''
<script>
function loadRiskEngineCard(){const s=(document.getElementById('market-symbol')||{}).value||'RELIANCE';fetch('/api/risk/check?symbol='+encodeURIComponent(s)).then(r=>r.json()).then(p=>{const el=document.getElementById('risk-engine-kv');if(!el)return;el.innerHTML=['allowed','mode','max_quantity_allowed','position_size','risk_amount','go_live_allowed'].map(k=>`<div><strong>${k}</strong>${p[k]}</div>`).join('')+`<div><strong>blocked_reasons</strong>${(p.blocked_reasons||[]).join(', ')}</div>`}).catch(()=>{})}
setInterval(loadRiskEngineCard,15000);loadRiskEngineCard();
</script>
'''


def main() -> None:
    if not WEB_APP.exists():
        raise SystemExit("web_app.py not found")
    BACKUP.mkdir(exist_ok=True)
    backup = BACKUP / f"web_app_before_phase5_{int(time.time())}.py"
    shutil.copy2(WEB_APP, backup)
    text = WEB_APP.read_text()
    marker = "from .runtime import InMemoryAuditStore, LivePaperTradingEngine, RuntimeConfig, ShadowRunValidator\n"
    if "from .risk_engine import RiskEngine" not in text:
        text = text.replace(marker, marker + IMPORTS, 1)
    if "def _risk_check_for_symbol" not in text:
        text = text.replace('\ndef run(host: str = "127.0.0.1", port: int = 8080) -> None:\n', HELPER + '\ndef run(host: str = "127.0.0.1", port: int = 8080) -> None:\n', 1)
    if 'path == "/api/risk/check"' not in text:
        route = '        elif path == "/api/safety/gates":\n            self._send_json(200, _safety_gates())\n'
        text = text.replace(route, route + '        elif path == "/api/risk/check":\n            self._send_json(200, _risk_check_for_symbol(_query_symbol(query)))\n', 1)
    if "risk = _risk_check_for_symbol" not in text:
        old = '        elif path == "/api/paper/order":\n            self._send_json(200, _paper_order(payload))\n'
        new = '        elif path == "/api/paper/order":\n            risk = _risk_check_for_symbol(str(payload.get("symbol", "RELIANCE")), int(payload.get("quantity", 1) or 1), str(payload.get("side", "BUY")))\n            if not risk.get("allowed"):\n                self._send_json(200, {"status": "BLOCKED", "blocked_reasons": risk.get("blocked_reasons", ()), "risk": risk, "go_live_allowed": False})\n            else:\n                self._send_json(200, _paper_order(payload))\n'
        text = text.replace(old, new, 1)
    if 'id="risk-engine-card"' not in text:
        text = text.replace('<section class="card strong shadow" id="paper-terminal">', CARD + '<section class="card strong shadow" id="paper-terminal">', 1)
    if "loadRiskEngineCard" not in text:
        text = text.replace("</body></html>", SCRIPT + "</body></html>", 1)
    WEB_APP.write_text(text)
    print(f"PHASE5_RISK_ENGINE_PATCHED backup={backup}")


if __name__ == "__main__":
    main()
