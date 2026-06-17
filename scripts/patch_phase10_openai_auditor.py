"""Patch Phase 10 OpenAI read-only auditor routes and dashboard card.

This patch is intentionally minimal and safe:
- It only adds read-only AI endpoints and UI.
- It does not enable broker mutations.
- It does not change go_live_allowed to true.
"""

from __future__ import annotations

from pathlib import Path

WEB_APP = Path("src/institutional_trading_platform/web_app.py")
BACKUP_DIR = Path(".alpha_gate_backups")

IMPORTS = """from .ai_error_doctor import accuracy_gate_rules, diagnose_local_error, latest_error_report
from .openai_auditor import OpenAIReadOnlyAuditor, audit_signal_with_openai, get_openai_auditor_config
"""

HELPERS = r'''

# PHASE10_OPENAI_AUDITOR_HELPERS_START
def _ai_health() -> dict[str, Any]:
    return OpenAIReadOnlyAuditor(get_openai_auditor_config()).health()


def _ai_accuracy_gates() -> dict[str, Any]:
    return accuracy_gate_rules()


def _ai_diagnose() -> dict[str, Any]:
    context = {
        "health": {"status": "ok", "service": "alpha-gate-x"},
        "live_readiness": _live_readiness(),
        "safety_gates": _safety_gates(),
        "paper_summary": _paper_status().get("account_summary", {}),
    }
    local = diagnose_local_error(context=context)
    openai_diagnosis = OpenAIReadOnlyAuditor(get_openai_auditor_config()).diagnose_error({"local_diagnosis": local, "context": context})
    return {
        "status": openai_diagnosis.get("status", local.get("status")),
        "local_diagnosis": local,
        "openai_diagnosis": openai_diagnosis,
        "safe_to_auto_patch": False,
        "requires_human_approval": True,
        "can_place_real_order": False,
        "go_live_allowed": False,
    }


def _ai_error_report() -> dict[str, Any]:
    report = latest_error_report()
    report["ai_health"] = _ai_health()
    report["openai_diagnosis"] = OpenAIReadOnlyAuditor(get_openai_auditor_config()).diagnose_error(report)
    report["safe_to_auto_patch"] = False
    report["requires_human_approval"] = True
    report["can_place_real_order"] = False
    report["go_live_allowed"] = False
    return report


def _ai_audit_signal_endpoint(payload: Mapping[str, Any]) -> dict[str, Any]:
    symbol = str(payload.get("symbol", "RELIANCE")).strip().upper() or "RELIANCE"
    signal = payload.get("signal") if isinstance(payload.get("signal"), Mapping) else {}
    quote = payload.get("market_quote") if isinstance(payload.get("market_quote"), Mapping) else _market_quote(symbol)
    history = payload.get("market_history") if isinstance(payload.get("market_history"), Mapping) else _market_history(symbol, interval="5minute")
    return audit_signal_with_openai(symbol=symbol, signal=signal, market_quote=quote, market_history=history)


def _ai_audit_for_signal_response(symbol: str, signal: Mapping[str, Any], *, history: Mapping[str, Any] | None = None) -> dict[str, Any]:
    normalized = (symbol or str(signal.get("symbol", "RELIANCE"))).strip().upper() or "RELIANCE"
    quote = _market_quote(normalized)
    hist = history if isinstance(history, Mapping) else _market_history(normalized, interval="5minute")
    return audit_signal_with_openai(symbol=normalized, signal=signal, market_quote=quote, market_history=hist)


def _apply_ai_audit_to_signal(signal: dict[str, Any], *, history: Mapping[str, Any] | None = None) -> dict[str, Any]:
    symbol = str(signal.get("symbol", "RELIANCE")).strip().upper() or "RELIANCE"
    audit = _ai_audit_for_signal_response(symbol, signal, history=history)
    signal["ai_audit"] = audit
    final_action = str(audit.get("final_action", "NO_TRADE")).upper()
    original_decision = str(signal.get("decision", DATA_UNAVAILABLE)).upper()
    if original_decision in {"BUY", "SELL"} and final_action in {"NO_TRADE", DATA_UNAVAILABLE}:
        signal["decision"] = final_action
        signal["validation_status"] = "BLOCKED_BY_AI_AUDITOR" if final_action == "NO_TRADE" else DATA_UNAVAILABLE
        reasons = list(signal.get("signal_reasons") or [])
        reasons.extend(audit.get("blocked_reasons") or [])
        signal["signal_reasons"] = tuple(dict.fromkeys(str(reason) for reason in reasons if str(reason)))
    signal["go_live_allowed"] = False
    return signal
# PHASE10_OPENAI_AUDITOR_HELPERS_END
'''

DASHBOARD_CARD = r'''
<section class="card shadow" id="openai-ai-auditor-card"><span class="badge info">OPENAI READ-ONLY</span><span class="badge danger">NO ORDER POWER</span><h2>OpenAI AI Safety Auditor</h2><p class="muted">AI can diagnose and audit signals only. It cannot modify files, enable live trading, or place broker orders.</p><div class="controls"><button onclick="loadAiHealth()">Check AI Health</button><button onclick="diagnoseAiError()">Diagnose Current Error</button><button onclick="auditCurrentSignal()">Audit Current Signal</button></div><div id="ai-health-kv" class="kv"></div><div class="card"><h3>Last AI Diagnosis / Audit</h3><pre id="ai-auditor-raw">/api/ai/health /api/ai/diagnose /api/ai/audit-signal</pre></div></section>
'''

DASHBOARD_JS = r'''
<script id="phase10-openai-auditor-ui">
(function(){
  function byId(id){ return document.getElementById(id); }
  function kv(target, obj, keys){
    var el = byId(target); if(!el) return;
    el.innerHTML = keys.map(function(k){ return '<div><strong>'+k+'</strong>' + ((obj && obj[k] !== undefined) ? obj[k] : 'DATA_UNAVAILABLE') + '</div>'; }).join('');
  }
  function raw(payload){ var el = byId('ai-auditor-raw'); if(el) el.textContent = JSON.stringify(payload, null, 2); }
  window.loadAiHealth = function(){
    fetch('/api/ai/health?t='+Date.now(), {cache:'no-store'}).then(function(r){ return r.json(); }).then(function(p){
      kv('ai-health-kv', p, ['status','model','auditor_enabled','autofix_enabled','can_modify_files','can_place_orders','go_live_allowed']); raw(p);
    }).catch(function(e){ raw({status:'ERROR', error:String(e), go_live_allowed:false}); });
  };
  window.diagnoseAiError = function(){
    fetch('/api/ai/diagnose?t='+Date.now(), {cache:'no-store'}).then(function(r){ return r.json(); }).then(raw).catch(function(e){ raw({status:'ERROR', error:String(e), go_live_allowed:false}); });
  };
  window.auditCurrentSignal = function(){
    var symbol = ((byId('market-symbol')||{}).value || 'RELIANCE').trim().toUpperCase();
    Promise.all([
      fetch('/api/signal/live?symbol='+encodeURIComponent(symbol)+'&t='+Date.now(), {cache:'no-store'}).then(function(r){ return r.json(); }),
      fetch('/api/broker/quote?symbol='+encodeURIComponent(symbol)+'&t='+Date.now(), {cache:'no-store'}).then(function(r){ return r.json(); }),
      fetch('/api/market/history?symbol='+encodeURIComponent(symbol)+'&interval=5minute&t='+Date.now(), {cache:'no-store'}).then(function(r){ return r.json(); })
    ]).then(function(items){
      return fetch('/api/ai/audit-signal', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({symbol:symbol, signal:items[0], market_quote:items[1], market_history:items[2]})});
    }).then(function(r){ return r.json(); }).then(raw).catch(function(e){ raw({status:'ERROR', error:String(e), go_live_allowed:false}); });
  };
  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', function(){ setTimeout(window.loadAiHealth, 700); });
  else setTimeout(window.loadAiHealth, 700);
})();
</script>
'''


def main() -> None:
    if not WEB_APP.exists():
        raise SystemExit(f"{WEB_APP} not found")

    BACKUP_DIR.mkdir(exist_ok=True)
    text = WEB_APP.read_text()
    (BACKUP_DIR / "web_app_before_phase10_openai_auditor.py").write_text(text)

    if "PHASE10_OPENAI_AUDITOR_IMPORTS" not in text:
        marker = "from .runtime import InMemoryAuditStore, LivePaperTradingEngine, RuntimeConfig, ShadowRunValidator\n"
        if marker not in text:
            raise SystemExit("import marker not found")
        text = text.replace(marker, marker + "# PHASE10_OPENAI_AUDITOR_IMPORTS\n" + IMPORTS, 1)

    if '"/api/ai/health"' not in text:
        get_marker = 'elif path == "/api/paper/settings":\n            self._send_json(200, _paper_settings_response(_query_symbol(query)))\n        else:'
        get_insert = 'elif path == "/api/paper/settings":\n            self._send_json(200, _paper_settings_response(_query_symbol(query)))\n        elif path == "/api/ai/health":\n            self._send_json(200, _ai_health())\n        elif path == "/api/ai/error-report":\n            self._send_json(200, _ai_error_report())\n        elif path == "/api/ai/accuracy-gates":\n            self._send_json(200, _ai_accuracy_gates())\n        elif path == "/api/ai/diagnose":\n            self._send_json(200, _ai_diagnose())\n        else:'
        if get_marker not in text:
            raise SystemExit("GET route marker not found")
        text = text.replace(get_marker, get_insert, 1)

    if '"/api/ai/audit-signal"' not in text:
        post_marker = 'elif path == "/api/paper/settings":\n            self._send_json(200, _paper_settings_update(payload))\n        else:'
        post_insert = 'elif path == "/api/paper/settings":\n            self._send_json(200, _paper_settings_update(payload))\n        elif path == "/api/ai/audit-signal":\n            self._send_json(200, _ai_audit_signal_endpoint(payload))\n        else:'
        if post_marker not in text:
            raise SystemExit("POST route marker not found")
        text = text.replace(post_marker, post_insert, 1)

    if "PHASE10_OPENAI_AUDITOR_HELPERS_START" not in text:
        helper_marker = "def _shadow_status() -> dict[str, Any]:"
        if helper_marker not in text:
            raise SystemExit("helper marker not found")
        text = text.replace(helper_marker, HELPERS + "\n\n" + helper_marker, 1)

    if "PHASE10_AI_SIGNAL_AUDIT_UNAVAILABLE" not in text:
        unavailable_marker = 'if history.get("validation_status") != "VALIDATED":\n        return _signal_unavailable(symbol, str(history.get("connection_status", DATA_UNAVAILABLE)), auto_requested=auto_requested)'
        unavailable_insert = 'if history.get("validation_status") != "VALIDATED":\n        payload = _signal_unavailable(symbol, str(history.get("connection_status", DATA_UNAVAILABLE)), auto_requested=auto_requested)\n        payload["phase10_marker"] = "PHASE10_AI_SIGNAL_AUDIT_UNAVAILABLE"\n        return _apply_ai_audit_to_signal(payload, history=history)'
        if unavailable_marker in text:
            text = text.replace(unavailable_marker, unavailable_insert, 1)

    if "PHASE10_AI_SIGNAL_AUDIT_VALIDATED" not in text:
        valid_marker = 'signal["auto_trade_state"] = _auto_trade_state(signal, auto_requested=auto_requested)\n    _paper_auto_trade_from_signal(signal)\n    return signal'
        valid_insert = 'signal["auto_trade_state"] = _auto_trade_state(signal, auto_requested=auto_requested)\n    signal["phase10_marker"] = "PHASE10_AI_SIGNAL_AUDIT_VALIDATED"\n    signal = _apply_ai_audit_to_signal(signal, history=history)\n    _paper_auto_trade_from_signal(signal)\n    return signal'
        if valid_marker in text:
            text = text.replace(valid_marker, valid_insert, 1)

    if "openai-ai-auditor-card" not in text:
        if "</main>" not in text:
            raise SystemExit("dashboard main close marker not found")
        text = text.replace("</main>", DASHBOARD_CARD + "\n</main>", 1)

    if "phase10-openai-auditor-ui" not in text:
        if "</body></html>" not in text:
            raise SystemExit("HTML body close marker not found")
        text = text.replace("</body></html>", DASHBOARD_JS + "\n</body></html>", 1)

    WEB_APP.write_text(text)
    print("✅ Phase 10 OpenAI read-only auditor patch applied")
    print("✅ Added /api/ai/health, /api/ai/diagnose, /api/ai/error-report, /api/ai/accuracy-gates")
    print("✅ Added POST /api/ai/audit-signal")
    print("✅ Real trading remains disabled; go_live_allowed remains false")


if __name__ == "__main__":
    main()
