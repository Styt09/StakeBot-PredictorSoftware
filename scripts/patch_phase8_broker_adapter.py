from __future__ import annotations

from pathlib import Path
import os
import shutil
import time

ROOT = Path(__file__).resolve().parents[1]
WEB_APP = ROOT / "src" / "institutional_trading_platform" / "web_app.py"
BACKUP = ROOT / ".alpha_gate_backups"

IMPORT_LINE = "from .broker_adapter import BrokerCredentials, ZerodhaReadOnlyAdapter, BlockedBrokerMutationAdapter\n"

HELPER = r'''

def _broker_adapter() -> ZerodhaReadOnlyAdapter:
    return ZerodhaReadOnlyAdapter(
        credentials=BrokerCredentials(
            api_key=os.environ.get("ZERODHA_API_KEY", ""),
            access_token=os.environ.get("ZERODHA_ACCESS_TOKEN", ""),
            user_id=os.environ.get("ZERODHA_USER_ID", ""),
        ),
        quote_provider=_market_quote,
    )


def _broker_mutation_block(payload: dict[str, Any], method: str) -> dict[str, Any]:
    blocker = BlockedBrokerMutationAdapter()
    if method == "place_order":
        return blocker.place_order(payload)
    if method == "modify_order":
        return blocker.modify_order(payload)
    if method == "cancel_order":
        return blocker.cancel_order(payload)
    if method == "exit_position":
        return blocker.exit_position(payload)
    return {"status": "BLOCKED", "reason": "BROKER_MUTATION_DISABLED", "broker_order_id": None, "go_live_allowed": False}
'''

CARD = '''
<section class="card strong shadow" id="broker-safety-card"><span class="badge warn">BROKER READ-ONLY</span><span class="badge danger">MUTATION DISABLED</span><h2>Broker Safety</h2><p class="muted">Zerodha adapter is read-only. Broker order mutations remain blocked.</p><div id="broker-safety-kv" class="kv"></div></section>
'''

SCRIPT = '''
<script>
function loadBrokerSafetyCard(){fetch('/api/broker/health').then(r=>r.json()).then(p=>{const el=document.getElementById('broker-safety-kv');if(!el)return;el.innerHTML=`<div><strong>broker</strong>${p.broker}</div><div><strong>connected</strong>${p.connected}</div><div><strong>read_only</strong>${p.read_only}</div><div><strong>mutation_enabled</strong>${p.mutation_enabled}</div><div><strong>status</strong>${p.status}</div><div><strong>last_checked_at</strong>${p.last_checked_at}</div><div><strong>go_live_allowed</strong>${p.go_live_allowed}</div>`}).catch(()=>{})}
setInterval(loadBrokerSafetyCard,15000);loadBrokerSafetyCard();
</script>
'''


def main() -> None:
    if not WEB_APP.exists():
        raise SystemExit("web_app.py not found")
    BACKUP.mkdir(exist_ok=True)
    backup = BACKUP / f"web_app_before_phase8_{int(time.time())}.py"
    shutil.copy2(WEB_APP, backup)
    text = WEB_APP.read_text()

    if IMPORT_LINE not in text:
        marker = "from .runtime import InMemoryAuditStore, LivePaperTradingEngine, RuntimeConfig, ShadowRunValidator\n"
        text = text.replace(marker, marker + IMPORT_LINE, 1)

    if "def _broker_adapter()" not in text:
        text = text.replace('\ndef run(host: str = "127.0.0.1", port: int = 8080) -> None:\n', HELPER + '\ndef run(host: str = "127.0.0.1", port: int = 8080) -> None:\n', 1)

    if 'path == "/api/broker/health"' not in text:
        marker_get = '        elif path == "/api/risk/check":\n            self._send_json(200, _risk_check_for_symbol(_query_symbol(query)))\n'
        insert_get = marker_get + '        elif path == "/api/broker/health":\n            self._send_json(200, _broker_adapter().health())\n        elif path == "/api/broker/quote":\n            self._send_json(200, _broker_adapter().quote(_query_symbol(query)))\n        elif path == "/api/broker/profile/status":\n            self._send_json(200, _broker_adapter().profile_status())\n        elif path == "/api/broker/margins/status":\n            self._send_json(200, _broker_adapter().margins_status())\n        elif path == "/api/broker/positions/status":\n            self._send_json(200, _broker_adapter().positions_status())\n'
        if marker_get not in text:
            raise SystemExit("risk check route marker not found; apply phase5 first")
        text = text.replace(marker_get, insert_get, 1)

    if 'path == "/api/broker/order/place"' not in text:
        marker_post = '        elif path == "/api/live/order/submit":\n            self._send_json(200, _live_order_submit(payload))\n'
        insert_post = marker_post + '        elif path == "/api/broker/order/place":\n            self._send_json(200, _broker_mutation_block(payload, "place_order"))\n        elif path == "/api/broker/order/modify":\n            self._send_json(200, _broker_mutation_block(payload, "modify_order"))\n        elif path == "/api/broker/order/cancel":\n            self._send_json(200, _broker_mutation_block(payload, "cancel_order"))\n        elif path == "/api/broker/position/exit":\n            self._send_json(200, _broker_mutation_block(payload, "exit_position"))\n'
        if marker_post not in text:
            raise SystemExit("live order submit route marker not found")
        text = text.replace(marker_post, insert_post, 1)

    if 'id="broker-safety-card"' not in text:
        text = text.replace('<section class="card strong shadow" id="paper-terminal">', CARD + '<section class="card strong shadow" id="paper-terminal">', 1)

    if "loadBrokerSafetyCard" not in text:
        text = text.replace("</body></html>", SCRIPT + "</body></html>", 1)

    WEB_APP.write_text(text)
    print(f"PHASE8_BROKER_ADAPTER_PATCHED backup={backup}")


if __name__ == "__main__":
    main()
