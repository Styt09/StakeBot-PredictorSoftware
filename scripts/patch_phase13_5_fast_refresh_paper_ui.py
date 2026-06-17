#!/usr/bin/env python3
"""Phase 13.5 UI fix: faster quote refresh + easier premium paper cockpit.

Safe UI-only patch. It does not enable live trading, does not change broker
mutation behavior, and keeps go_live_allowed=false.
"""
from __future__ import annotations

from pathlib import Path
from time import time
import shutil

WEB_APP = Path("src/institutional_trading_platform/web_app.py")
BACKUP_DIR = Path(".alpha_gate_backups")
CSS_MARKER = "/* PHASE 13.5 FAST PAPER COCKPIT */"
JS_MARKER = "// PHASE 13.5 FAST PAPER COCKPIT HELPERS"
HTML_MARKER = "<!-- PHASE 13.5 PAPER COCKPIT -->"

CSS = r'''
    /* PHASE 13.5 FAST PAPER COCKPIT */
    #paper-terminal{border:1px solid rgba(52,211,153,.34)!important;background:linear-gradient(135deg,rgba(6,78,59,.20),rgba(15,23,42,.86))!important}
    #paper-terminal h2{font-size:clamp(1.6rem,3.6vw,2.6rem)!important;color:#bbf7d0!important}
    .paper-cockpit{display:grid;grid-template-columns:1.1fr .9fr;gap:14px;margin:14px 0 18px}
    .paper-hero{background:linear-gradient(135deg,rgba(16,185,129,.18),rgba(14,165,233,.12));border:1px solid rgba(52,211,153,.32);border-radius:22px;padding:16px;box-shadow:0 16px 50px rgba(0,0,0,.24)}
    .paper-hero-title{display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap;margin-bottom:10px}.paper-hero-title strong{font-size:1.25rem;color:#ecfeff}
    .paper-step-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-top:12px}.paper-step{border:1px solid rgba(148,163,184,.22);background:rgba(2,6,23,.42);border-radius:16px;padding:11px;min-height:76px}.paper-step b{display:block;color:#67e8f9;font-size:.72rem;text-transform:uppercase;letter-spacing:.08em}.paper-step span{display:block;color:#dbeafe;font-size:.88rem;margin-top:4px}
    .paper-action-pad{display:grid;grid-template-columns:1fr 1fr;gap:10px}.paper-action-pad button{min-height:56px;font-size:.95rem}.paper-action-pad .buy-paper{background:linear-gradient(135deg,rgba(5,150,105,.95),rgba(45,212,191,.36))!important}.paper-action-pad .sell-paper{background:linear-gradient(135deg,rgba(220,38,38,.88),rgba(251,113,133,.28))!important}.paper-action-pad .copy-paper{grid-column:span 2;background:linear-gradient(135deg,rgba(37,99,235,.86),rgba(103,232,249,.30))!important}.paper-qty-chip{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}.paper-qty-chip button{width:auto;min-height:36px;padding:8px 12px;border-radius:999px;background:rgba(2,6,23,.72)!important}
    .paper-note{margin-top:10px;color:#bbf7d0;background:rgba(5,150,105,.12);border:1px solid rgba(52,211,153,.22);border-radius:14px;padding:10px;font-size:.86rem}
    #paper-summary.kv div{background:linear-gradient(135deg,rgba(2,6,23,.72),rgba(6,78,59,.20))!important;border-color:rgba(52,211,153,.24)!important}
    #paper-summary.kv div strong{color:#a7f3d0!important}
    @media(max-width:850px){.paper-cockpit{grid-template-columns:1fr}.paper-step-grid{grid-template-columns:1fr 1fr}.paper-action-pad{grid-template-columns:1fr}.paper-action-pad .copy-paper{grid-column:span 1}}
'''

HTML = r'''
<!-- PHASE 13.5 PAPER COCKPIT -->
<div class="paper-cockpit">
  <div class="paper-hero">
    <div class="paper-hero-title"><strong>Easy Paper Trading Cockpit</strong><span class="badge buy">VIRTUAL ONLY</span></div>
    <p class="muted">Simple 4-step paper flow: select symbol → copy signal → set quantity → submit virtual order. No broker order is placed.</p>
    <div class="paper-step-grid">
      <div class="paper-step"><b>Step 1</b><span>Pick symbol from watchlist</span></div>
      <div class="paper-step"><b>Step 2</b><span>Generate live signal</span></div>
      <div class="paper-step"><b>Step 3</b><span>Copy signal to paper</span></div>
      <div class="paper-step"><b>Step 4</b><span>Submit virtual order</span></div>
    </div>
    <div class="paper-note">Safety lock: Paper orders use virtual money only. LIVE remains NO-GO and go_live_allowed=false.</div>
  </div>
  <div class="paper-hero">
    <div class="paper-action-pad">
      <button class="copy-paper" onclick="copySignalToPaper()">Copy Current Signal → Paper Form</button>
      <button class="buy-paper" onclick="quickPaperOrder('BUY')">Quick Virtual BUY</button>
      <button class="sell-paper" onclick="quickPaperOrder('SELL')">Quick Virtual SELL / Close</button>
    </div>
    <div class="paper-qty-chip">
      <button onclick="setPaperQty(1)">Qty 1</button>
      <button onclick="setPaperQty(5)">Qty 5</button>
      <button onclick="setPaperQty(10)">Qty 10</button>
      <button onclick="setPaperQty(25)">Qty 25</button>
    </div>
    <p class="tiny muted">Quick buttons fill the existing paper order form below. Review values before submission.</p>
  </div>
</div>
'''

JS = r'''
// PHASE 13.5 FAST PAPER COCKPIT HELPERS
function safeNumberFromText(id){const el=document.getElementById(id);if(!el)return 0;const n=Number(String(el.textContent||el.value||'').replace(/[^0-9.\-]/g,''));return Number.isFinite(n)?n:0}
function setPaperQty(q){const el=document.getElementById('paper-qty');if(el)el.value=String(q)}
function copySignalToPaper(){
  try{
    const raw=document.getElementById('signal-raw');
    const p=raw&&raw.textContent?JSON.parse(raw.textContent):{};
    const decision=(p.decision||p.action||'BUY').toUpperCase();
    const symbol=(document.getElementById('market-symbol')?.value||p.symbol||'RELIANCE').toUpperCase();
    const ltp=safeNumberFromText('quote-ltp');
    document.getElementById('paper-symbol').value=symbol;
    document.getElementById('paper-side').value=decision==='SELL'?'SELL':'BUY';
    document.getElementById('paper-entry').value=Number(p.entry||ltp||0).toFixed(2);
    document.getElementById('paper-sl').value=Number(p.stop_loss||0).toFixed(2);
    document.getElementById('paper-t1').value=Number(p.target_1||p.target||0).toFixed(2);
    document.getElementById('paper-t2').value=Number(p.target_2||0).toFixed(2);
    document.getElementById('paper-order-result').textContent='Copied signal to paper form. Review values, then submit virtual order only.';
  }catch(e){document.getElementById('paper-order-result').textContent='Could not copy signal: '+e}
}
function quickPaperOrder(side){
  const symbol=(document.getElementById('market-symbol')?.value||'RELIANCE').toUpperCase();
  document.getElementById('paper-symbol').value=symbol;
  document.getElementById('paper-side').value=side;
  if(!Number(document.getElementById('paper-entry').value||0)){
    const ltp=safeNumberFromText('quote-ltp');
    if(ltp)document.getElementById('paper-entry').value=ltp.toFixed(2);
  }
  document.getElementById('paper-order-result').textContent='Quick '+side+' prepared. Submitting virtual paper order...';
  submitPaperOrder();
}
'''


def replace_once(text: str, old: str, new: str) -> str:
    return text.replace(old, new, 1) if old in text else text


def main() -> None:
    if not WEB_APP.exists():
        raise SystemExit(f"Missing file: {WEB_APP}")
    BACKUP_DIR.mkdir(exist_ok=True)
    backup = BACKUP_DIR / f"web_app_before_fast_refresh_paper_ui_{int(time())}.py"
    shutil.copy2(WEB_APP, backup)

    text = WEB_APP.read_text(encoding="utf-8")

    # Faster visible refresh, but not zero-delay. This is still REST polling, not tick-by-tick websocket.
    text = text.replace("const quoteIntervalMs=()=>document.hidden?15000:3000;", "const quoteIntervalMs=()=>document.hidden?5000:1000;")
    text = text.replace("pollingTimers.signal=setInterval(s,15000);", "pollingTimers.signal=setInterval(s,7000);")
    text = text.replace("pollingTimers.chart=setInterval(c,60000);", "pollingTimers.chart=setInterval(c,30000);")
    text = text.replace("pollingTimers.paper=setInterval(p,3000);", "pollingTimers.paper=setInterval(p,1500);")

    if CSS_MARKER not in text:
        text = text.replace("  </style>", CSS + "\n  </style>", 1)

    if HTML_MARKER not in text:
        anchor = '<div id="paper-summary" class="kv"></div>'
        if anchor not in text:
            raise SystemExit("Could not find paper summary anchor. No backend logic changed.")
        text = text.replace(anchor, HTML + anchor, 1)

    if JS_MARKER not in text:
        js_anchor = "function livePayload()"
        if js_anchor not in text:
            raise SystemExit("Could not find JS anchor. No backend logic changed.")
        text = text.replace(js_anchor, JS + "\n" + js_anchor, 1)

    WEB_APP.write_text(text, encoding="utf-8")
    print("✅ Fast refresh + premium paper cockpit applied")
    print("✅ Quote visible refresh: 1 second REST polling")
    print("✅ Paper refresh: 1.5 seconds")
    print("✅ Paper cockpit added: copy signal, quick virtual BUY/SELL, qty chips")
    print("✅ Backend trading logic unchanged")
    print("✅ LIVE remains NO-GO / go_live_allowed=false")
    print(f"Backup: {backup}")


if __name__ == "__main__":
    main()
