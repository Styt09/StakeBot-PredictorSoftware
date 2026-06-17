from __future__ import annotations

from pathlib import Path
import shutil
import time

ROOT = Path(__file__).resolve().parents[1]
WEB_APP = ROOT / "src" / "institutional_trading_platform" / "web_app.py"
BACKUP = ROOT / ".alpha_gate_backups"

IMPORT_LINE = "from .shadow_trading import ShadowTradingEngine, ShadowTradingState\n"

HELPER = r'''

_SHADOW_STATE = ShadowTradingState()
_SHADOW_ENGINE = ShadowTradingEngine(_SHADOW_STATE)


def _shadow_quote(symbol: str) -> dict[str, Any]:
    quote = _market_quote(symbol)
    status = quote.get("validation_status") or quote.get("status") or "DATA_UNAVAILABLE"
    ltp = quote.get("ltp") or quote.get("last_price") or quote.get("lastPrice")
    return {"symbol": symbol, "ltp": ltp, "validation_status": status, "raw": quote, "go_live_allowed": False}


def _shadow_evaluate(payload: dict[str, Any]) -> dict[str, Any]:
    symbol = str(payload.get("symbol", "RELIANCE")).upper()
    side = str(payload.get("side", "BUY")).upper()
    quantity = int(payload.get("quantity", 1) or 1)
    provider = ExistingDataProvider(_market_quote, _market_history)
    health = MarketDataHealthService(provider).health(symbol)
    raw_signal = _live_signal(symbol, auto_requested=False)
    safe_signal = safe_signal_from_existing_signal(symbol, raw_signal, health)
    risk = RiskEngine().evaluate(RiskInput(
        symbol=symbol,
        side=side,
        quantity=quantity,
        signal=safe_signal,
        market_health=health,
        account_state={},
        open_positions=tuple(_SHADOW_STATE.open_positions),
        order_path="SHADOW",
        kill_switch_active=_kill_switch_active(),
    ))
    quote = _shadow_quote(symbol)
    return _SHADOW_ENGINE.evaluate_order(symbol=symbol, side=side, quantity=quantity, quote=quote, safe_signal=safe_signal, risk=risk)
'''

CARD = '''
<section class="card strong shadow" id="shadow-trading-card"><span class="badge warn">SHADOW MODE — NO REAL MONEY USED</span><span class="badge danger">BROKER SUBMIT DISABLED</span><h2>Shadow Trading Layer</h2><p class="muted">Theoretical live-data validation only. No Zerodha order submission.</p><div id="shadow-trading-kv" class="kv"></div></section>
'''

SCRIPT = '''
<script>
function loadShadowTradingCard(){fetch('/api/shadow/status').then(r=>r.json()).then(p=>{const el=document.getElementById('shadow-trading-kv');if(!el)return;const orders=p.orders||[];const last=orders.length?orders[orders.length-1]:{};el.innerHTML=`<div><strong>last shadow order</strong>${last.status||'NONE'}</div><div><strong>open shadow positions</strong>${(p.open_positions||[]).length}</div><div><strong>shadow realized pnl</strong>${p.realized_pnl}</div><div><strong>shadow unrealized pnl</strong>${p.unrealized_pnl}</div><div><strong>blocked reasons</strong>${(last.blocked_reasons||[]).join(', ')||'NONE'}</div><div><strong>go_live_allowed</strong>${p.go_live_allowed}</div>`}).catch(()=>{})}
setInterval(loadShadowTradingCard,10000);loadShadowTradingCard();
</script>
'''


def main() -> None:
    if not WEB_APP.exists():
        raise SystemExit("web_app.py not found")
    BACKUP.mkdir(exist_ok=True)
    backup = BACKUP / f"web_app_before_phase7_{int(time.time())}.py"
    shutil.copy2(WEB_APP, backup)
    text = WEB_APP.read_text()

    marker = "from .runtime import InMemoryAuditStore, LivePaperTradingEngine, RuntimeConfig, ShadowRunValidator\n"
    if IMPORT_LINE not in text:
        text = text.replace(marker, marker + IMPORT_LINE, 1)

    if "_SHADOW_ENGINE = ShadowTradingEngine" not in text:
        text = text.replace('\ndef run(host: str = "127.0.0.1", port: int = 8080) -> None:\n', HELPER + '\ndef run(host: str = "127.0.0.1", port: int = 8080) -> None:\n', 1)

    if 'path == "/api/shadow/orders"' not in text:
        marker_get = '        elif path == "/api/shadow/status":\n            self._send_json(200, _shadow_status())\n'
        insert_get = marker_get + '        elif path == "/api/shadow/orders":\n            self._send_json(200, {"orders": tuple(_SHADOW_STATE.orders), "go_live_allowed": False})\n        elif path == "/api/shadow/trades":\n            self._send_json(200, {"trades": tuple(_SHADOW_STATE.closed_trades), "go_live_allowed": False})\n        elif path == "/api/shadow/report":\n            self._send_json(200, _SHADOW_ENGINE.report())\n'
        if marker_get not in text:
            raise SystemExit("shadow status route marker not found")
        text = text.replace(marker_get, insert_get, 1)

    if 'path == "/api/shadow/evaluate"' not in text:
        marker_post = '        elif path == "/api/paper/order":\n'
        insert_post = '        elif path == "/api/shadow/evaluate":\n            self._send_json(200, _shadow_evaluate(payload))\n        elif path == "/api/shadow/reset":\n            self._send_json(200, _SHADOW_ENGINE.reset())\n' + marker_post
        if marker_post not in text:
            raise SystemExit("paper order post route marker not found")
        text = text.replace(marker_post, insert_post, 1)

    if 'id="shadow-trading-card"' not in text:
        text = text.replace('<section class="card strong shadow" id="paper-terminal">', CARD + '<section class="card strong shadow" id="paper-terminal">', 1)

    if "loadShadowTradingCard" not in text:
        text = text.replace("</body></html>", SCRIPT + "</body></html>", 1)

    WEB_APP.write_text(text)
    print(f"PHASE7_SHADOW_TRADING_PATCHED backup={backup}")


if __name__ == "__main__":
    main()
