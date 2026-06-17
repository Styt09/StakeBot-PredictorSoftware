from __future__ import annotations

from pathlib import Path
import shutil
import time

ROOT = Path(__file__).resolve().parents[1]
WEB_APP = ROOT / "src" / "institutional_trading_platform" / "web_app.py"
BACKUP = ROOT / ".alpha_gate_backups"

IMPORT_LINE = "from .readiness_gates import ReadinessGateEvaluator, ReadinessInputs\n"

HELPER = r'''

def _readiness_inputs() -> ReadinessInputs:
    broker = _broker_adapter().health() if "_broker_adapter" in globals() else {}
    mutation = _broker_mutation_block({"symbol": "RELIANCE"}, "place_order") if "_broker_mutation_block" in globals() else {"status": "BLOCKED", "broker_order_id": None, "go_live_allowed": False}
    audit = _audit_report() if "_audit_report" in globals() else {}
    kill = _persistent_kill_switch_status() if "_persistent_kill_switch_status" in globals() else {"active": False, "go_live_allowed": False}
    return ReadinessInputs(
        broker_health=broker,
        market_data_health=_market_data_health_for_readiness(),
        kill_switch_status=kill,
        audit_report=audit,
        live_order_status=_live_order_submit({}),
        broker_mutation_status=mutation,
        paper_status=_paper_status(),
        shadow_status=_SHADOW_ENGINE.status() if "_SHADOW_ENGINE" in globals() else _shadow_status(),
        public_config=getSafePublicConfig() if "getSafePublicConfig" in globals() else {},
    )


def _market_data_health_for_readiness() -> dict[str, Any]:
    try:
        provider = ExistingDataProvider(_market_quote, _market_history)
        return MarketDataHealthService(provider).health("RELIANCE")
    except Exception as exc:
        return {"state": "DATA_UNAVAILABLE", "error_type": type(exc).__name__, "go_live_allowed": False}


def _readiness_gates() -> dict[str, Any]:
    return ReadinessGateEvaluator().evaluate(_readiness_inputs())


def _readiness_report() -> dict[str, Any]:
    evaluator = ReadinessGateEvaluator()
    gates = evaluator.evaluate(_readiness_inputs())
    return evaluator.report(gates)


def _readiness_checklist() -> dict[str, Any]:
    evaluator = ReadinessGateEvaluator()
    gates = evaluator.evaluate(_readiness_inputs())
    return evaluator.checklist(gates)
'''

CARD = '''
<section class="card strong shadow" id="readiness-gates-card"><span class="badge info">READINESS GATES</span><span class="badge danger">LIVE VERDICT NO-GO</span><h2>Operational Readiness</h2><p class="muted">Reports PAPER/SHADOW readiness while keeping live trading disabled.</p><div id="readiness-gates-kv" class="kv"></div></section>
'''

SCRIPT = '''
<script>
function loadReadinessGatesCard(){fetch('/api/readiness/gates').then(r=>r.json()).then(p=>{const el=document.getElementById('readiness-gates-kv');if(!el)return;el.innerHTML=`<div><strong>paper ready</strong>${p.paper_ready}</div><div><strong>shadow ready</strong>${p.shadow_ready}</div><div><strong>live ready</strong>${p.live_ready}</div><div><strong>live verdict</strong>${p.live_verdict}</div><div><strong>top blocked reasons</strong>${(p.blocked_reasons||[]).slice(0,4).join(', ')}</div><div><strong>go_live_allowed</strong>${p.go_live_allowed}</div>`}).catch(()=>{})}
setInterval(loadReadinessGatesCard,15000);loadReadinessGatesCard();
</script>
'''


def main() -> None:
    if not WEB_APP.exists():
        raise SystemExit("web_app.py not found")
    BACKUP.mkdir(exist_ok=True)
    backup = BACKUP / f"web_app_before_phase11_{int(time.time())}.py"
    shutil.copy2(WEB_APP, backup)
    text = WEB_APP.read_text()

    if IMPORT_LINE not in text:
        marker = "from .runtime import InMemoryAuditStore, LivePaperTradingEngine, RuntimeConfig, ShadowRunValidator\n"
        text = text.replace(marker, marker + IMPORT_LINE, 1)

    if "def _readiness_inputs()" not in text:
        text = text.replace('\ndef run(host: str = "127.0.0.1", port: int = 8080) -> None:\n', HELPER + '\ndef run(host: str = "127.0.0.1", port: int = 8080) -> None:\n', 1)

    if 'path == "/api/readiness/gates"' not in text:
        marker_get = '        elif path == "/api/status":\n'
        route = '        elif path == "/api/readiness/gates":\n            self._send_json(200, _readiness_gates())\n        elif path == "/api/readiness/report":\n            self._send_json(200, _readiness_report())\n        elif path == "/api/readiness/go-live-checklist":\n            self._send_json(200, _readiness_checklist())\n'
        if marker_get not in text:
            raise SystemExit("status route marker not found")
        text = text.replace(marker_get, route + marker_get, 1)

    if 'id="readiness-gates-card"' not in text:
        text = text.replace('<section class="card strong shadow" id="paper-terminal">', CARD + '<section class="card strong shadow" id="paper-terminal">', 1)

    if "loadReadinessGatesCard" not in text:
        text = text.replace("</body></html>", SCRIPT + "</body></html>", 1)

    WEB_APP.write_text(text)
    print(f"PHASE11_READINESS_GATES_PATCHED backup={backup}")


if __name__ == "__main__":
    main()
