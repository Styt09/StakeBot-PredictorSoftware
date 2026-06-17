from __future__ import annotations

from pathlib import Path
import shutil
import time

ROOT = Path(__file__).resolve().parents[1]
WEB_APP = ROOT / "src" / "institutional_trading_platform" / "web_app.py"
BACKUP = ROOT / ".alpha_gate_backups"

IMPORT_LINE = "from .durable_audit_log import DurableAuditLog, AuditWriteError\n"

HELPER = r'''

_AUDIT_LOG = DurableAuditLog()

def _audit_write(event_type: str, source: str, status: str, **fields: Any) -> dict[str, Any]:
    return _AUDIT_LOG.write_event({"event_type": event_type, "source": source, "status": status, **fields, "go_live_allowed": False})

def _audit_recent(limit: int = 100) -> dict[str, Any]:
    return _AUDIT_LOG.recent(limit)

def _audit_report() -> dict[str, Any]:
    return _AUDIT_LOG.report()

def _audit_export() -> dict[str, Any]:
    return _AUDIT_LOG.export_events()

def _audit_limit(query: dict[str, Any]) -> int:
    try:
        return min(max(int((query.get("limit") or [100])[0]), 1), 500)
    except Exception:
        return 100
'''

CARD = '''
<section class="card strong shadow" id="audit-log-card"><span class="badge info">DURABLE AUDIT LOG</span><span class="badge warn">EVIDENCE REPORTS</span><h2>Audit Evidence</h2><p class="muted">Safety decisions are written to local JSONL evidence logs. Secrets are masked before persistence.</p><div id="audit-log-kv" class="kv"></div></section>
'''

SCRIPT = '''
<script>
function loadAuditLogCard(){fetch('/api/audit/report').then(r=>r.json()).then(p=>{const el=document.getElementById('audit-log-kv');if(!el)return;const last=p.last_event||{};el.innerHTML=`<div><strong>last event type</strong>${last.event_type||'NONE'}</div><div><strong>last status</strong>${last.status||'NONE'}</div><div><strong>total events</strong>${p.total_events}</div><div><strong>recent blocked reasons</strong>${Object.keys(p.counts_by_blocked_reason||{}).slice(0,4).join(', ')||'NONE'}</div><div><strong>audit storage path</strong>${p.audit_storage_path}</div><div><strong>go_live_allowed</strong>${p.go_live_allowed}</div>`}).catch(()=>{})}
setInterval(loadAuditLogCard,10000);loadAuditLogCard();
</script>
'''


def main() -> None:
    if not WEB_APP.exists():
        raise SystemExit("web_app.py not found")
    BACKUP.mkdir(exist_ok=True)
    backup = BACKUP / f"web_app_before_phase10_{int(time.time())}.py"
    shutil.copy2(WEB_APP, backup)
    text = WEB_APP.read_text()

    if IMPORT_LINE not in text:
        marker = "from .runtime import InMemoryAuditStore, LivePaperTradingEngine, RuntimeConfig, ShadowRunValidator\n"
        text = text.replace(marker, marker + IMPORT_LINE, 1)

    if "_AUDIT_LOG = DurableAuditLog()" not in text:
        text = text.replace('\ndef run(host: str = "127.0.0.1", port: int = 8080) -> None:\n', HELPER + '\ndef run(host: str = "127.0.0.1", port: int = 8080) -> None:\n', 1)

    if 'event_type": "SYSTEM_START"' not in text:
        text = text.replace('def run(host: str = "127.0.0.1", port: int = 8080) -> None:\n    ThreadingHTTPServer((host, port), AlphaGateXRequestHandler).serve_forever()\n', 'def run(host: str = "127.0.0.1", port: int = 8080) -> None:\n    _audit_write("SYSTEM_START", "WEB_APP", "PASS", metadata={"host": host, "port": port})\n    ThreadingHTTPServer((host, port), AlphaGateXRequestHandler).serve_forever()\n', 1)

    if 'path == "/api/audit/recent"' not in text:
        marker_get = '        elif path == "/api/status":\n            self._send_json(200, {"active_scope": "live_market_signal_paper_trading", "go_live_allowed": False})\n'
        insert_get = marker_get + '        elif path == "/api/audit/recent":\n            self._send_json(200, _audit_recent(_audit_limit(query)))\n        elif path == "/api/audit/report":\n            self._send_json(200, _audit_report())\n        elif path == "/api/audit/export":\n            self._send_json(200, _audit_export())\n'
        if marker_get not in text:
            raise SystemExit("status route marker not found")
        text = text.replace(marker_get, insert_get, 1)

    if 'id="audit-log-card"' not in text:
        text = text.replace('<section class="card strong shadow" id="paper-terminal">', CARD + '<section class="card strong shadow" id="paper-terminal">', 1)

    if "loadAuditLogCard" not in text:
        text = text.replace("</body></html>", SCRIPT + "</body></html>", 1)

    # Lightweight integration wrappers. If exact markers are absent, endpoints still work.
    if 'AUDIT_BROKER_HEALTH_CHECKED' not in text:
        text = text.replace('self._send_json(200, _broker_adapter().health())', 'self._send_json(200, (lambda p: (_audit_write("BROKER_HEALTH_CHECKED", "BROKER_ADAPTER", str(p.get("status", "UNKNOWN")), metadata=p), p)[1])(_broker_adapter().health()))')
        text += '\n# AUDIT_BROKER_HEALTH_CHECKED\n'

    if 'AUDIT_LIVE_ORDER_BLOCKED' not in text:
        text = text.replace('self._send_json(200, _live_order_submit(payload))', 'self._send_json(200, (lambda p: (_audit_write("LIVE_ORDER_BLOCKED", "LIVE_ORDER", str(p.get("status", "BLOCKED")), blocked_reasons=tuple(p.get("block_reasons", ("LIVE_ORDER_BLOCKED",))), metadata=p), p)[1])(_live_order_submit(payload)))')
        text += '\n# AUDIT_LIVE_ORDER_BLOCKED\n'

    WEB_APP.write_text(text)
    print(f"PHASE10_AUDIT_LOG_PATCHED backup={backup}")


if __name__ == "__main__":
    main()
