"""Patch Phase 11 safe trade-plan enrichment into web_app.py."""

from __future__ import annotations

from pathlib import Path

WEB_APP = Path("src/institutional_trading_platform/web_app.py")
BACKUP_DIR = Path(".alpha_gate_backups")

IMPORT_LINE = "from .safe_trade_plan import enrich_signal_with_safe_trade_plan\n"

HELPER_BLOCK = r'''

# PHASE11_SAFE_TRADE_PLAN_HELPERS_START
def _phase11_enrich_signal(symbol: str, signal: Mapping[str, Any], history: Mapping[str, Any]) -> dict[str, Any]:
    normalized = (symbol or str(signal.get("symbol", "RELIANCE"))).strip().upper() or "RELIANCE"
    quote = _market_quote(normalized)
    enriched = enrich_signal_with_safe_trade_plan(signal, symbol=normalized, market_quote=quote, market_history=history)
    enriched["phase11_marker"] = "PHASE11_SAFE_TRADE_PLAN_ENRICHED"
    enriched["go_live_allowed"] = False
    return enriched
# PHASE11_SAFE_TRADE_PLAN_HELPERS_END
'''

DASHBOARD_CARD = r'''
<section class="card shadow" id="phase11-signal-plan-card"><span class="badge info">SAFE TRADE PLAN</span><span class="badge danger">PAPER / SHADOW ONLY</span><h2>Safe Signal Trade Plan</h2><p class="muted">Entry, stop-loss, targets, risk-reward, and AI audit status are shown only when validated quote and candle evidence exists.</p><div id="phase11-signal-plan-kv" class="kv"></div><pre id="phase11-signal-plan-raw">Waiting for /api/signal/live</pre></section>
'''

DASHBOARD_JS = r'''
<script id="phase11-safe-trade-plan-ui">
(function(){
  function byId(id){ return document.getElementById(id); }
  function kv(target, obj, keys){
    var el = byId(target); if(!el) return;
    el.innerHTML = keys.map(function(k){ return '<div><strong>'+k+'</strong>' + ((obj && obj[k] !== undefined) ? obj[k] : 'DATA_UNAVAILABLE') + '</div>'; }).join('');
  }
  function renderPhase11Signal(p){
    var plan = p.safe_trade_plan || {};
    var ai = p.ai_audit || {};
    kv('phase11-signal-plan-kv', {
      decision: p.decision,
      entry: p.entry,
      stop_loss: p.stop_loss,
      target_1: p.target_1,
      target_2: p.target_2,
      risk_reward: p.risk_reward,
      confidence: p.confidence_score || p.confidence,
      confidence_grade: p.confidence_grade,
      expected_move_points: p.expected_move_points,
      ai_final_action: ai.final_action,
      ai_status: ai.status,
      blocked_reasons: (ai.blocked_reasons || plan.blocked_reasons || p.signal_reasons || []).join(' | '),
      go_live_allowed: false
    }, ['decision','entry','stop_loss','target_1','target_2','risk_reward','confidence','confidence_grade','expected_move_points','ai_final_action','ai_status','blocked_reasons','go_live_allowed']);
    var raw = byId('phase11-signal-plan-raw'); if(raw) raw.textContent = JSON.stringify({signal:p, safe_trade_plan:plan, ai_audit:ai}, null, 2);
  }
  var previousLoadLiveSignal = window.loadLiveSignal;
  window.loadLiveSignal = function(isAuto){
    var symbol = ((byId('market-symbol')||{}).value || 'RELIANCE').trim().toUpperCase();
    return fetch('/api/signal/live?symbol='+encodeURIComponent(symbol)+'&t='+Date.now(), {cache:'no-store'})
      .then(function(r){ return r.json(); })
      .then(function(p){
        var d = p.decision || p.final_action || 'DATA_UNAVAILABLE';
        var dec = byId('signal-decision');
        if(dec){ dec.textContent = d; dec.className = 'signal-decision ' + (d === 'BUY' ? 'decision-buy' : d === 'SELL' ? 'decision-sell' : 'decision-wait'); }
        var status = byId('signal-status');
        if(status){ status.textContent = p.validation_status || 'DATA_UNAVAILABLE'; status.className = 'badge ' + (p.validation_status === 'VALIDATED' ? 'buy' : 'warn'); }
        var reasons = p.signal_reasons || p.safe_trade_plan_blocked_reasons || (p.ai_audit && p.ai_audit.blocked_reasons) || [];
        if(typeof reasons === 'string') reasons = [reasons];
        var summary = byId('signal-summary'); if(summary) summary.textContent = reasons.join(' · ') || 'Signal checked. No fabricated signal generated.';
        var conf = Number(p.confidence_score || p.confidence || 0);
        var confText = byId('confidence-text'); if(confText) confText.textContent = String(conf);
        var meter = byId('confidence-meter'); if(meter) meter.style.width = Math.max(0, Math.min(100, conf)) + '%';
        kv('signal-kv', p, ['entry','stop_loss','target_1','target_2','risk_reward','expected_move_points','confidence_grade','timestamp','data_source']);
        kv('indicator-kv', p.indicators || {}, ['ema_9','ema_21','vwap','rsi_14','atr_14','volume_confirmation','trend_direction']);
        kv('auto-trade-state', p.auto_trade_state || {}, ['requested','state','eligible','reason']);
        var raw = byId('signal-raw'); if(raw) raw.textContent = JSON.stringify(p, null, 2);
        renderPhase11Signal(p);
        return p;
      })
      .catch(function(e){
        if(typeof previousLoadLiveSignal === 'function') return previousLoadLiveSignal(isAuto);
        var raw = byId('phase11-signal-plan-raw'); if(raw) raw.textContent = 'Signal API error: ' + e;
      });
  };
  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', function(){ setTimeout(function(){ window.loadLiveSignal(false); }, 900); });
  else setTimeout(function(){ window.loadLiveSignal(false); }, 900);
})();
</script>
'''


def main() -> None:
    if not WEB_APP.exists():
        raise SystemExit(f"{WEB_APP} not found")
    BACKUP_DIR.mkdir(exist_ok=True)
    text = WEB_APP.read_text()
    (BACKUP_DIR / "web_app_before_phase11_safe_trade_plan.py").write_text(text)

    if "safe_trade_plan import enrich_signal_with_safe_trade_plan" not in text:
        marker = "from .runtime import InMemoryAuditStore, LivePaperTradingEngine, RuntimeConfig, ShadowRunValidator\n"
        if marker not in text:
            raise SystemExit("runtime import marker not found")
        text = text.replace(marker, marker + IMPORT_LINE, 1)

    if "PHASE11_SAFE_TRADE_PLAN_HELPERS_START" not in text:
        helper_marker = "def _shadow_status() -> dict[str, Any]:"
        if helper_marker not in text:
            raise SystemExit("helper marker not found")
        text = text.replace(helper_marker, HELPER_BLOCK + "\n" + helper_marker, 1)

    # Enrich unavailable signal path before AI audit if Phase 10 is present.
    unavailable_marker = 'payload["phase10_marker"] = "PHASE10_AI_SIGNAL_AUDIT_UNAVAILABLE"\n        return _apply_ai_audit_to_signal(payload, history=history)'
    unavailable_insert = 'payload["phase10_marker"] = "PHASE10_AI_SIGNAL_AUDIT_UNAVAILABLE"\n        payload = _phase11_enrich_signal(symbol, payload, history)\n        return _apply_ai_audit_to_signal(payload, history=history)'
    if unavailable_marker in text and "payload = _phase11_enrich_signal(symbol, payload, history)" not in text:
        text = text.replace(unavailable_marker, unavailable_insert, 1)

    # Enrich validated signal path before AI audit.
    validated_marker = 'signal["phase10_marker"] = "PHASE10_AI_SIGNAL_AUDIT_VALIDATED"\n    signal = _apply_ai_audit_to_signal(signal, history=history)'
    validated_insert = 'signal["phase10_marker"] = "PHASE10_AI_SIGNAL_AUDIT_VALIDATED"\n    signal = _phase11_enrich_signal(symbol, signal, history)\n    signal = _apply_ai_audit_to_signal(signal, history=history)'
    if validated_marker in text and "signal = _phase11_enrich_signal(symbol, signal, history)" not in text:
        text = text.replace(validated_marker, validated_insert, 1)

    # Fallback if Phase 10 patch was not applied.
    fallback_marker = 'signal["auto_trade_state"] = _auto_trade_state(signal, auto_requested=auto_requested)\n    _paper_auto_trade_from_signal(signal)\n    return signal'
    fallback_insert = 'signal["auto_trade_state"] = _auto_trade_state(signal, auto_requested=auto_requested)\n    signal = _phase11_enrich_signal(symbol, signal, history)\n    if "_apply_ai_audit_to_signal" in globals():\n        signal = _apply_ai_audit_to_signal(signal, history=history)\n    _paper_auto_trade_from_signal(signal)\n    return signal'
    if fallback_marker in text and "_phase11_enrich_signal(symbol, signal, history)" not in text:
        text = text.replace(fallback_marker, fallback_insert, 1)

    if "phase11-signal-plan-card" not in text:
        marker = '<section class="card strong shadow" id="paper-terminal"'
        if marker in text:
            text = text.replace(marker, DASHBOARD_CARD + "\n" + marker, 1)
        elif "</main>" in text:
            text = text.replace("</main>", DASHBOARD_CARD + "\n</main>", 1)
        else:
            raise SystemExit("dashboard insertion marker not found")

    if "phase11-safe-trade-plan-ui" not in text:
        if "</body></html>" not in text:
            raise SystemExit("HTML close marker not found")
        text = text.replace("</body></html>", DASHBOARD_JS + "\n</body></html>", 1)

    WEB_APP.write_text(text)
    print("✅ Phase 11 safe trade plan patch applied")
    print("✅ Signal payload will be enriched with entry, stop_loss, targets, risk_reward")
    print("✅ AI audit still runs after safe trade plan and may only downgrade")
    print("✅ Real trading remains disabled; go_live_allowed remains false")


if __name__ == "__main__":
    main()
