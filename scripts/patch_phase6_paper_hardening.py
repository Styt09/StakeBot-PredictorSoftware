from __future__ import annotations

from pathlib import Path
import shutil
import time

ROOT = Path(__file__).resolve().parents[1]
WEB_APP = ROOT / "src" / "institutional_trading_platform" / "web_app.py"
BACKUP = ROOT / ".alpha_gate_backups"

CARD = '''
<section class="card strong shadow" id="paper-execution-hardening-card"><span class="badge buy">PAPER MODE — NO REAL MONEY USED</span><span class="badge danger">REAL ORDERS DISABLED</span><h2>Paper Execution Hardening</h2><p class="muted">Paper orders must pass risk checks before virtual execution. Brokerage and slippage are placeholders.</p><div id="paper-exec-kv" class="kv"></div></section>
'''

SCRIPT = '''
<script>
function loadPaperExecutionCard(){fetch('/api/paper/status').then(r=>r.json()).then(p=>{const el=document.getElementById('paper-exec-kv');if(!el)return;const orders=p.orders||[];const last=orders.length?orders[orders.length-1]:{};el.innerHTML=`<div><strong>last paper order status</strong>${last.status||'NONE'}</div><div><strong>open paper positions</strong>${(p.open_positions||[]).length}</div><div><strong>realized pnl</strong>${p.realized_pnl}</div><div><strong>unrealized pnl</strong>${p.unrealized_pnl}</div><div><strong>brokerage placeholder</strong>${p.brokerage_placeholder||0}</div><div><strong>slippage placeholder</strong>${p.slippage_placeholder||0}</div>`}).catch(()=>{})}
setInterval(loadPaperExecutionCard,5000);loadPaperExecutionCard();
</script>
'''


def main() -> None:
    if not WEB_APP.exists():
        raise SystemExit("web_app.py not found")
    BACKUP.mkdir(exist_ok=True)
    backup = BACKUP / f"web_app_before_phase6_{int(time.time())}.py"
    shutil.copy2(WEB_APP, backup)
    text = WEB_APP.read_text()

    if 'path == "/api/paper/orders"' not in text:
        marker = '        elif path == "/api/paper/statement":\n            self._send_json(200, _paper_statement())\n'
        insert = marker + '        elif path == "/api/paper/orders":\n            self._send_json(200, {"orders": tuple(_PAPER.get("orders", ())), "go_live_allowed": False})\n        elif path == "/api/paper/trades":\n            self._send_json(200, {"trades": tuple(_PAPER.get("closed_trades", ())), "go_live_allowed": False})\n'
        if marker not in text:
            raise SystemExit("paper statement route marker not found")
        text = text.replace(marker, insert, 1)

    if 'id="paper-execution-hardening-card"' not in text:
        text = text.replace('<section class="card strong shadow" id="paper-terminal">', CARD + '<section class="card strong shadow" id="paper-terminal">', 1)

    if "loadPaperExecutionCard" not in text:
        text = text.replace("</body></html>", SCRIPT + "</body></html>", 1)

    WEB_APP.write_text(text)
    print(f"PHASE6_PAPER_HARDENING_PATCHED backup={backup}")


if __name__ == "__main__":
    main()
