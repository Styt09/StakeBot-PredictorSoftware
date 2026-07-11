"""Stdlib web application for ALPHA-GATE X trading, signal, and paper terminal."""

from __future__ import annotations

import csv
import json
import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from .aegis_platform import AegisQuantPlatform
from .broker import ReadOnlyKiteTickerWrapper
from .domain import AssetClass, Instrument, MarketBar, Venue
from .live_signal_engine import accuracy_report as _strict_accuracy_report
from .live_signal_engine import signal_from_candles as _strict_signal_from_candles
from .live_signal_engine import signal_unavailable as _strict_signal_unavailable
from .runtime import InMemoryAuditStore, LivePaperTradingEngine, RuntimeConfig, ShadowRunValidator

DATA_UNAVAILABLE = "DATA_UNAVAILABLE"

FALLBACK_SYMBOLS = (
    "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "SBIN", "AXISBANK",
    "KOTAKBANK", "LT", "ITC", "HINDUNILVR", "BHARTIARTL", "ASIANPAINT",
    "MARUTI", "TATAMOTORS", "M&M", "BAJFINANCE", "HCLTECH", "WIPRO",
    "TECHM", "SUNPHARMA", "CIPLA", "ADANIENT", "ADANIPORTS", "ULTRACEMCO",
    "POWERGRID", "NTPC", "COALINDIA", "ONGC", "BPCL", "NIFTY", "BANKNIFTY", "FINNIFTY",
)

HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>ALPHA-GATE X SHADOW TRADING PLATFORM</title>
  <style>
    :root{color-scheme:dark;--bg:#06101f;--panel:rgba(10,22,38,.88);--panel2:rgba(13,29,51,.96);--line:rgba(148,163,184,.24);--text:#edf7ff;--muted:#9eb5d1;--accent:#67e8f9;--accent2:#6ee7b7;--warn:#fbbf24;--danger:#fb7185;--buy:#22c55e;--sell:#ef4444;--shadow:0 22px 70px rgba(0,0,0,.38)}
    *{box-sizing:border-box}body{margin:0;font-family:Inter,ui-sans-serif,system-ui,-apple-system,Segoe UI,sans-serif;background:radial-gradient(circle at 12% 0%,rgba(103,232,249,.18),transparent 34%),radial-gradient(circle at 85% 8%,rgba(110,231,183,.14),transparent 30%),linear-gradient(135deg,#06101f 0%,#071426 50%,#050b15 100%);color:var(--text);min-height:100vh}header{padding:24px min(5vw,70px) 16px;border-bottom:1px solid var(--line)}main{padding:18px min(5vw,70px) 46px}h1{margin:8px 0 4px;font-size:clamp(1.8rem,5vw,4.4rem);letter-spacing:.045em;line-height:1.02}h2{margin:.2rem 0 .35rem;color:var(--accent2);font-weight:900}h3{margin:.2rem 0 .6rem}p{color:#d8e7f7}.topbar{position:sticky;top:0;z-index:30;display:flex;gap:8px;align-items:center;justify-content:space-between;flex-wrap:wrap;margin:-18px min(-5vw,-70px) 18px;padding:10px min(5vw,70px);background:rgba(5,10,20,.82);backdrop-filter:blur(16px);border-bottom:1px solid var(--line)}.badge{display:inline-flex;width:max-content;align-items:center;gap:6px;border-radius:999px;padding:6px 10px;background:#0e243f;color:var(--accent2);font-size:.72rem;font-weight:950;letter-spacing:.08em;text-transform:uppercase}.badge.warn{color:var(--warn);background:rgba(251,191,36,.12)}.badge.danger{color:var(--danger);background:rgba(251,113,133,.13)}.badge.info{color:var(--accent);background:rgba(103,232,249,.11)}.badge.buy{color:#bbf7d0;background:rgba(34,197,94,.18)}.badge.sell{color:#fecaca;background:rgba(239,68,68,.18)}.grid,.watchlist,.terminal-grid,.paper-grid,.principles{display:grid;grid-template-columns:repeat(auto-fit,minmax(245px,1fr));gap:14px}.card{background:var(--panel);border:1px solid var(--line);border-radius:22px;padding:16px;box-shadow:var(--shadow);backdrop-filter:blur(16px)}.strong{background:var(--panel2)}.shadow{margin-top:20px}.kv{display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:10px}.kv div{background:rgba(5,17,31,.72);border:1px solid var(--line);border-radius:14px;padding:10px;min-height:56px}.kv strong{color:#dbeafe;display:block;font-size:.75rem;opacity:.9;text-transform:lowercase}.controls{display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:10px;margin:12px 0}.field{display:grid;gap:6px}.field label{font-size:.72rem;font-weight:950;color:#dbeafe;text-transform:uppercase;letter-spacing:.06em}.field input,.field select,button,input,select,summary{border-radius:13px;border:1px solid var(--line);padding:11px 12px;background:rgba(5,17,31,.88);color:var(--text);min-height:42px}button{cursor:pointer;font-weight:950}button:hover,summary:hover{border-color:rgba(103,232,249,.55)}button[disabled]{cursor:not-allowed;opacity:.45}button.danger{background:#3a1320;color:#fecdd3;border-color:#7f1d1d}.quote-value{font-size:clamp(2.1rem,9vw,4.8rem);font-weight:1000;line-height:1}.signal-decision{font-size:clamp(2.4rem,10vw,5.8rem);font-weight:1000;line-height:.95;letter-spacing:.03em}.decision-buy{color:var(--buy)}.decision-sell{color:var(--sell)}.decision-wait{color:var(--warn)}.profit{color:var(--buy);font-weight:950}.loss{color:var(--sell);font-weight:950}.meter{height:14px;background:#081827;border:1px solid var(--line);border-radius:999px;overflow:hidden}.meter>div{height:100%;background:linear-gradient(90deg,var(--danger),var(--warn),var(--accent2));width:0%;transition:width .25s ease}canvas{width:100%;height:280px;background:linear-gradient(180deg,rgba(6,24,44,.92),rgba(3,10,20,.92));border:1px solid var(--line);border-radius:18px}.muted{color:var(--muted)}pre{white-space:pre-wrap;overflow:auto;color:#d7e9ff;background:rgba(3,10,20,.86);padding:12px;border-radius:14px;max-height:320px}.paper-row{border-bottom:1px solid var(--line);padding:10px 0}.paper-row:last-child{border-bottom:none}.suggestions{display:none;position:absolute;z-index:50;background:#071523;border:1px solid var(--line);border-radius:14px;box-shadow:var(--shadow);max-height:260px;overflow:auto;width:100%;margin-top:4px}.suggestion{padding:12px;border-bottom:1px solid var(--line);cursor:pointer}.suggestion:hover{background:rgba(103,232,249,.12)}.search-wrap{position:relative}.debug-json{margin-top:12px}.debug-json summary{width:max-content}.live-head{display:grid;grid-template-columns:1fr;gap:12px}.unlock-list{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px;margin:12px 0 16px}.unlock-list div{background:rgba(5,17,31,.70);border:1px dashed rgba(251,191,36,.35);border-radius:14px;padding:12px}details.future-roadmap{margin-top:24px}details.future-roadmap summary{cursor:pointer;font-weight:950;list-style:none}@media(min-width:900px){.terminal-grid{grid-template-columns:.85fr 1.15fr}.paper-grid{grid-template-columns:1fr 1fr}.live-head{grid-template-columns:1.05fr .95fr}}@media(max-width:620px){header{padding:16px 14px}.principles{display:none}.card{border-radius:18px;padding:14px}.controls{grid-template-columns:1fr}.kv{grid-template-columns:1fr 1fr}.quote-value{font-size:3rem}pre{font-size:.74rem;max-height:210px}}
  </style>
</head>
<body>
<header><span class="badge info">ZERODHA LIVE DATA WHEN CONNECTED · LIVE TRADING FAIL-CLOSED</span><h1>ALPHA-GATE X SHADOW TRADING PLATFORM</h1><h2>Live Market → Live Signal Engine → Paper Trading → Manual Review</h2><p>No fabricated accuracy, confidence, profitability, expected move, OI, PCR, IV, depth, flow, or alpha. Missing evidence returns <strong>DATA_UNAVAILABLE</strong>; weak evidence returns <strong>NO_TRADE</strong>.</p></header>
<main>
<section class="topbar"><span class="badge info" id="connection-badge">CONNECTION · READY</span><span class="badge info" id="polling-badge">LIVE POLLING ON</span><span class="badge warn" id="refresh-badge">Last refresh: never · Next: --s</span><span class="badge danger" id="auto-trade-badge">AUTO TRADE · OFF</span></section>
<section class="principles"><div class="card"><strong>Runtime Mode</strong><p>Paper/shadow validation first. Real live auto trading is disabled by default.</p></div><div class="card"><strong>Data Source</strong><p>Every quote, candle, signal, and paper trade includes data_source and timestamp.</p></div><div class="card"><strong>Validation Status</strong><p>BUY/SELL signals appear only when real candle evidence is validated.</p></div></section>

<section class="card strong shadow" id="live-terminal">
  <span class="badge info">LIVE MARKET WEB APP</span><h2>Live Market Dashboard</h2>
  <p class="muted">Search any clean NSE stock/index. Suggestions load only while typing for lag-free mobile use.</p>
  <div class="live-head">
    <div class="card">
      <div class="field search-wrap"><label>Search Stock / Index</label><input id="market-symbol" value="RELIANCE" autocomplete="off" placeholder="Type RELIANCE, TCS, NIFTY..." oninput="queueSymbolSearch(this.value)" onfocus="queueSymbolSearch(this.value)" /><div id="symbol-suggestions" class="suggestions"></div></div>
      <div class="controls"><button onclick="refreshMarketData()">Refresh Price</button><button onclick="loadChart()">Load Chart</button><button onclick="loadLiveSignal()">Generate Live Signal</button></div>
      <div class="controls"><select id="auto-refresh-toggle" onchange="setAutoRefresh(this.value==='true')"><option value="true">Auto Refresh ON</option><option value="false">Auto Refresh OFF</option></select><span class="badge info" id="refresh-status">LIVE POLLING ON</span><span class="badge warn" id="last-refresh">Last refresh: never</span><span class="badge warn" id="next-refresh">Next refresh: --s</span></div>
    </div>
    <div class="card"><span id="quote-status" class="badge warn">DATA_UNAVAILABLE</span><h3 id="quote-symbol">RELIANCE</h3><div id="quote-ltp" class="quote-value">--</div><div id="quote-change" class="muted">Change unavailable</div><div id="quote-kv" class="kv" style="margin-top:12px"></div></div>
  </div>
  <div class="card shadow"><h3>Candlestick Chart</h3><span id="chart-status" class="badge warn">Live data unavailable</span><canvas id="market-chart" width="900" height="320"></canvas><div id="chart-message" class="muted">No fabricated chart data is rendered.</div></div>
  <h3>Quick Watchlist</h3><div id="watchlist" class="watchlist"></div>
  <details class="debug-json"><summary>Show Debug JSON</summary><pre id="market-raw">Market payload will appear here. /api/market/symbols /api/market/watchlist /api/market/quote /api/market/history</pre></details>
</section>

<section class="card strong shadow" id="signal-terminal"><span class="badge info">LIVE SIGNAL ENGINE</span><h2>Trading Terminal Signal</h2><div class="terminal-grid"><div class="card"><span id="signal-status" class="badge warn">NO SIGNAL</span><div id="signal-decision" class="signal-decision decision-wait">--</div><p id="signal-summary" class="muted">Tap Generate Live Signal.</p><div class="meter"><div id="confidence-meter"></div></div><p><strong>Confidence:</strong> <span id="confidence-text">0</span>%</p><div id="signal-kv" class="kv"></div></div><div class="card"><h3>Indicators & Reasons</h3><div id="indicator-kv" class="kv"></div><details class="debug-json"><summary>Show Signal JSON</summary><pre id="signal-raw">Signal payload will appear here. /api/signal/live</pre></details></div></div><div class="card shadow"><span class="badge danger">AUTO-TRADE TOGGLE · DEFAULT OFF</span><h3>Real Auto-Trade Control</h3><p class="muted">Real orders remain fail-closed.</p><div class="controls"><select id="auto-trade-toggle"><option value="false">REAL AUTO TRADE OFF</option><option value="true">REAL AUTO TRADE ON</option></select><button onclick="loadLiveSignal()">Recheck Real Auto-Trade Gate</button></div><div id="auto-trade-state" class="kv"></div></div></section>

<section class="card strong shadow" id="paper-terminal"><span class="badge buy">PAPER MODE · VIRTUAL MONEY ONLY</span><span class="badge danger">REAL ORDERS DISABLED</span><h2>Paper Trading Terminal</h2><p class="muted">Manual paper BUY/SELL, target/stop tracking, paper auto-trade, and statement ledger. This never calls real broker order placement APIs. Virtual paper money only.</p><div id="paper-summary" class="kv"></div><div class="controls"><div class="field"><label>Add virtual balance</label><input id="paper-add-amount" type="number" value="10000" min="1" step="100" /></div><button onclick="addPaperBalance()">Add Virtual Balance</button><button class="danger" onclick="resetPaperAccount()">Reset Paper Account</button></div>
  <div class="paper-grid"><div class="card"><h3>Manual Paper Order</h3><div class="controls"><div class="field"><label>Stock / Index</label><input id="paper-symbol" value="RELIANCE" placeholder="Selected symbol" onchange="selectMarketSymbol(this.value)" /></div><div class="field"><label>Side</label><select id="paper-side"><option>BUY</option><option>SELL</option></select></div><div class="field"><label>Quantity</label><input id="paper-qty" type="number" value="1" min="1" /></div><div class="field"><label>Entry Price optional</label><input id="paper-entry" type="number" value="0" min="0" step="0.05" placeholder="0 = latest quote" /></div><div class="field"><label>Stop Loss</label><input id="paper-sl" type="number" value="0" min="0" step="0.05" /></div><div class="field"><label>Target 1</label><input id="paper-t1" type="number" value="0" min="0" step="0.05" /></div><div class="field"><label>Target 2</label><input id="paper-t2" type="number" value="0" min="0" step="0.05" /></div><button onclick="submitPaperOrder()">Submit Paper Order</button></div><details class="debug-json"><summary>Show Paper Order JSON</summary><pre id="paper-order-result">Paper order result will appear here.</pre></details></div>
  <div class="card"><h3>Paper Auto Settings</h3><p class="muted">Virtual paper auto-trade only. Real orders disabled.</p><div class="controls"><div class="field"><label>Auto-trade mode</label><select id="setting-auto"><option value="false">OFF</option><option value="true">ON</option></select></div><div class="field"><label>Position sizing mode</label><select id="setting-sizing"><option>FIXED_QUANTITY</option><option>FIXED_AMOUNT</option></select></div><div class="field"><label>Fixed quantity</label><input id="setting-fixed-qty" type="number" value="1" min="1" /></div><div class="field"><label>Fixed amount</label><input id="setting-fixed-amount" type="number" value="1000" min="1" /></div><div class="field"><label>Target mode</label><select id="setting-target-mode"><option>PERCENT</option><option>POINTS</option></select></div><div class="field"><label>Target value</label><input id="setting-target-value" type="number" value="1" min="0" step="0.05" /></div><div class="field"><label>Stop loss mode</label><select id="setting-sl-mode"><option>PERCENT</option><option>POINTS</option></select></div><div class="field"><label>Stop loss value</label><input id="setting-sl-value" type="number" value="0.5" min="0" step="0.05" /></div><div class="field"><label>Max open positions</label><input id="setting-max-open" type="number" value="1" min="1" /></div><div class="field"><label>Max trades per day</label><input id="setting-max-trades" type="number" value="5" min="1" /></div><div class="field"><label>Max daily paper loss</label><input id="setting-max-loss" type="number" value="1000" min="0" /></div><button onclick="savePaperSettings()">Save Settings</button></div><h3>Calculated Preview</h3><div id="paper-auto-preview" class="kv"></div><details class="debug-json"><summary>Show Settings JSON</summary><pre id="paper-settings-raw">/api/paper/settings</pre></details></div></div>
  <div class="paper-grid"><div class="card"><h3>Open Positions</h3><div id="paper-open-positions" class="muted">No open paper positions.</div></div><div class="card"><h3>Closed Trades</h3><div id="paper-closed-trades" class="muted">No closed paper trades.</div></div></div><div class="card"><h3>Paper Statement</h3><div id="paper-ledger" class="muted">No ledger entries yet.</div><details class="debug-json"><summary>Show Statement JSON</summary><pre id="paper-raw">/api/paper/status /api/paper/statement /api/paper/order /api/paper/balance/add /api/paper/reset /api/paper/position/close /api/paper/auto-trade/toggle</pre></details></div></section>

<section class="card shadow" id="manual-order-terminal"><span class="badge danger">LIVE MONEY RISK · MANUAL APPROVAL ONLY</span><h2>Real Live Trading Control Panel</h2><p>Real live order submit remains blocked unless every strict gate passes.</p><div class="controls"><button onclick="loadLiveReadiness()">Check Live Readiness</button><button onclick="previewLiveOrder()">Preview LIMIT Order</button><button id="submit-live-order" onclick="submitLiveOrder()" disabled>Submit Live Order</button><button class="danger" onclick="enableKillSwitch()">Enable Kill Switch</button><button onclick="resetKillSwitch()">Reset Kill Switch</button></div><div class="action-result"><strong>Last Action Result</strong><div id="last-action-line">No action yet.</div></div><div class="controls"><input id="live-symbol" value="RELIANCE" /><select id="live-side"><option>BUY</option><option>SELL</option></select><input id="live-qty" value="1" type="number" min="1" /><input id="live-price" value="1" type="number" min="0" step="0.05" /></div><div id="live-readiness" class="kv"></div><details class="debug-json"><summary>Show Live Gate JSON</summary><pre id="live-raw">/api/shadow/status /api/live/readiness /api/demo</pre></details></section>

<details class="card strong future-roadmap" id="future-modules"><summary>Future Institutional Modules · intentionally locked</summary><p class="muted"><strong>Future modules are intentionally locked until enough live evidence is collected. No fake validation.</strong></p><div class="unlock-list"><div><strong>Drift Detection</strong><br>Requires 30–60 days signal/outcome logs.</div><div><strong>Automated Retraining</strong><br>Requires validated drift + backtest gates.</div><div><strong>Machine Learning Foundation</strong><br>Requires labeled dataset and OOS validation.</div><div><strong>Ensembles</strong><br>Requires multiple validated ML models.</div><div><strong>Advanced AI</strong><br>Requires validated ML + governance gates.</div><div><strong>Financial LLM</strong><br>Requires verified financial/news data source.</div></div><div id="phases" class="grid"></div></details>
<section class="card shadow"><span class="badge warn">READ-ONLY · GO-LIVE DISABLED</span><h2>Real Shadow Runtime Status</h2><div id="shadow-status" class="kv"></div><details class="debug-json"><summary>Show Shadow JSON</summary><pre id="shadow-raw">Loading shadow runtime status...</pre></details></section>
</main>
<script>
let latestPreviewId=null;let autoRefreshEnabled=true;let lastSuccessfulRefresh=null;let nextQuoteRefreshAt=Date.now();let marketSymbols=['RELIANCE','TCS','INFY','HDFCBANK','ICICIBANK','SBIN','AXISBANK','KOTAKBANK','LT','ITC','NIFTY','BANKNIFTY','FINNIFTY'];let symbolSearchTimer=null;const pollingTimers={quote:null,signal:null,chart:null,paper:null,countdown:null};
const renderKv=(target,status,keys)=>{const el=document.getElementById(target);if(!el)return;el.innerHTML=keys.map(k=>`<div><strong>${k}</strong>${status&&status[k]!==undefined?status[k]:'DATA_UNAVAILABLE'}</div>`).join('')};const postJson=(url,payload)=>fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload||{})}).then(r=>r.json());const stampRefresh=()=>{lastSuccessfulRefresh=new Date();document.getElementById('last-refresh').textContent=`Last refresh: ${lastSuccessfulRefresh.toLocaleTimeString()}`;document.getElementById('refresh-badge').textContent=`Last refresh: ${lastSuccessfulRefresh.toLocaleTimeString()} · Next: --s`};const setPollingStatus=(s,k='info')=>{document.getElementById('refresh-status').textContent=s;document.getElementById('polling-badge').textContent=s;document.getElementById('polling-badge').className=`badge ${k}`};const clearPollingTimers=()=>{Object.keys(pollingTimers).forEach(k=>{if(pollingTimers[k]){clearInterval(pollingTimers[k]);pollingTimers[k]=null}})};const quoteIntervalMs=()=>document.hidden?15000:3000;function updateCountdown(){const r=Math.max(0,Math.ceil((nextQuoteRefreshAt-Date.now())/1000));document.getElementById('next-refresh').textContent=`Next refresh: ${r}s`;if(lastSuccessfulRefresh)document.getElementById('refresh-badge').textContent=`Last refresh: ${lastSuccessfulRefresh.toLocaleTimeString()} · Next: ${r}s`}function setAutoRefresh(e){autoRefreshEnabled=e;if(e)startAutoRefresh();else{clearPollingTimers();setPollingStatus('PAUSED','warn')}}function startAutoRefresh(){clearPollingTimers();setPollingStatus('LIVE POLLING ON','info');const q=()=>{if(!autoRefreshEnabled)return;nextQuoteRefreshAt=Date.now()+quoteIntervalMs();refreshMarketData(true)};const s=()=>autoRefreshEnabled&&loadLiveSignal(true);const c=()=>autoRefreshEnabled&&!document.hidden&&loadChart(true);const p=()=>autoRefreshEnabled&&loadPaperStatus(true);q();s();c();p();loadPaperSettings();pollingTimers.quote=setInterval(q,quoteIntervalMs());pollingTimers.signal=setInterval(s,15000);pollingTimers.chart=setInterval(c,60000);pollingTimers.paper=setInterval(p,3000);pollingTimers.countdown=setInterval(updateCountdown,1000)}document.addEventListener('visibilitychange',()=>{if(autoRefreshEnabled)startAutoRefresh()});
function renderSymbolSuggestions(symbols){const box=document.getElementById('symbol-suggestions');if(!box)return;if(!symbols||!symbols.length){box.style.display='none';box.innerHTML='';return}box.innerHTML=symbols.slice(0,50).map(s=>`<div class="suggestion" onclick="pickSymbol('${s}')">${s}</div>`).join('');box.style.display='block'}function queueSymbolSearch(q){clearTimeout(symbolSearchTimer);symbolSearchTimer=setTimeout(()=>searchSymbols(q),250)}function searchSymbols(q){q=(q||'').trim().toUpperCase();if(q.length<1){renderSymbolSuggestions([]);return}fetch('/api/market/symbols?q='+encodeURIComponent(q)).then(r=>r.json()).then(p=>renderSymbolSuggestions(p.symbols||[])).catch(()=>renderSymbolSuggestions([]))}function pickSymbol(symbol){selectMarketSymbol(symbol);renderSymbolSuggestions([])}function renderWatchlist(p){const symbols=(p.symbols&&p.symbols.length?p.symbols:marketSymbols).slice(0,12);document.getElementById('watchlist').innerHTML=symbols.map(symbol=>`<div class="card" onclick="selectMarketSymbol('${symbol}')"><span class="badge info">LIVE READY</span><h3>${symbol}</h3><p class="muted">Tap to load quote + signal.</p></div>`).join('')}function selectMarketSymbol(symbol){symbol=(symbol||'RELIANCE').trim().toUpperCase();document.getElementById('market-symbol').value=symbol;document.getElementById('live-symbol').value=symbol;document.getElementById('paper-symbol').value=symbol;refreshMarketData();loadChart();loadLiveSignal();loadPaperStatus();loadPaperSettings()}
function refreshMarketData(isAuto=false){const symbol=document.getElementById('market-symbol').value;fetch(`/api/market/quote?symbol=${encodeURIComponent(symbol)}`).then(r=>r.json()).then(p=>{document.getElementById('quote-symbol').textContent=p.symbol||symbol;document.getElementById('quote-ltp').textContent=p.ltp??'--';document.getElementById('quote-change').textContent=p.change_percent==='DATA_UNAVAILABLE'?'Change unavailable':`${p.change_percent}%`;document.getElementById('quote-status').textContent=p.validation_status||'DATA_UNAVAILABLE';renderKv('quote-kv',p,['open','high','low','close','volume','last_update','data_source','connection_status']);document.getElementById('market-raw').textContent=JSON.stringify(p,null,2);stampRefresh();setPollingStatus('LIVE POLLING ON','info');loadPaperStatus(true)})}
function loadChart(isAuto=false){const symbol=document.getElementById('market-symbol').value;fetch(`/api/market/history?symbol=${encodeURIComponent(symbol)}&interval=minute`).then(r=>r.json()).then(p=>{drawChart(p.candles||[]);document.getElementById('chart-status').textContent=p.validation_status==='VALIDATED'?'CHART READY':'Live data unavailable';document.getElementById('chart-message').textContent=p.validation_status==='VALIDATED'?`Showing Zerodha 1-minute candles for ${symbol}`:'Live data unavailable. No fabricated chart data is rendered.'})}
function drawChart(candles){const canvas=document.getElementById('market-chart');const ctx=canvas.getContext('2d');ctx.clearRect(0,0,canvas.width,canvas.height);ctx.fillStyle='#071523';ctx.fillRect(0,0,canvas.width,canvas.height);ctx.strokeStyle='rgba(148,163,184,.22)';for(let i=0;i<6;i++){const y=30+i*48;ctx.beginPath();ctx.moveTo(28,y);ctx.lineTo(canvas.width-28,y);ctx.stroke()}if(!candles.length){ctx.fillStyle='#9eb5d1';ctx.font='26px system-ui';ctx.fillText('Live candle data unavailable',46,148);ctx.font='16px system-ui';ctx.fillText('No fabricated chart data is rendered.',46,178);return}const rows=candles.map(c=>({open:Number(c.open),high:Number(c.high),low:Number(c.low),close:Number(c.close)})).filter(c=>[c.open,c.high,c.low,c.close].every(Number.isFinite)).slice(-80);const max=Math.max(...rows.map(c=>c.high));const min=Math.min(...rows.map(c=>c.low));const range=Math.max(max-min,1);const left=34,right=canvas.width-34,top=24,bottom=canvas.height-34;const step=(right-left)/Math.max(rows.length,1);const yFor=price=>bottom-((price-min)/range)*(bottom-top);rows.forEach((c,i)=>{const x=left+i*step+step/2;const o=yFor(c.open),cl=yFor(c.close),h=yFor(c.high),l=yFor(c.low);ctx.strokeStyle=c.close>=c.open?'#6ee7b7':'#fb7185';ctx.fillStyle=ctx.strokeStyle;ctx.beginPath();ctx.moveTo(x,h);ctx.lineTo(x,l);ctx.stroke();ctx.fillRect(x-3,Math.min(o,cl),6,Math.max(2,Math.abs(cl-o)))})}
function loadLiveSignal(isAuto=false){const symbol=document.getElementById('market-symbol').value;fetch(`/api/signal/live?symbol=${encodeURIComponent(symbol)}`).then(r=>r.json()).then(p=>{const d=p.decision||'DATA_UNAVAILABLE';const el=document.getElementById('signal-decision');el.textContent=d;el.className='signal-decision '+(d==='BUY'?'decision-buy':d==='SELL'?'decision-sell':'decision-wait');document.getElementById('signal-status').textContent=p.validation_status||'DATA_UNAVAILABLE';document.getElementById('signal-summary').textContent=(p.signal_reasons||[]).join(' · ')||'No signal reasons available.';document.getElementById('confidence-text').textContent=p.confidence_score??0;document.getElementById('confidence-meter').style.width=`${Math.max(0,Math.min(100,Number(p.confidence_score||0)))}%`;renderKv('signal-kv',p,['entry','stop_loss','target_1','target_2','risk_reward','timestamp','data_source']);renderKv('indicator-kv',p.indicators||{},['ema_9','ema_21','vwap','rsi_14','atr_14','volume_confirmation','trend_direction']);renderKv('auto-trade-state',p.auto_trade_state||{},['requested','state','eligible','reason']);document.getElementById('signal-raw').textContent=JSON.stringify(p,null,2);loadPaperStatus(true)})}
function livePayload(){return{symbol:document.getElementById('live-symbol').value,exchange:'NSE',side:document.getElementById('live-side').value,quantity:Number(document.getElementById('live-qty').value),order_type:'LIMIT',price:Number(document.getElementById('live-price').value),product:'MIS'}}function setActionResult(label,p){document.getElementById('last-action-line').textContent=`${new Date().toLocaleTimeString()} · ${label}`;document.getElementById('live-raw').textContent=JSON.stringify(p,null,2)}function loadLiveReadiness(){fetch('/api/live/readiness').then(r=>r.json()).then(p=>{renderKv('live-readiness',p,['mode','zerodha_credentials_visible','access_token_visible','expected_user_id_match','instruments_csv_exists','live_trading_env_enabled','manual_approval_required','kill_switch_status','go_live_allowed']);setActionResult('Readiness checked',p)})}function previewLiveOrder(){postJson('/api/live/order/preview',livePayload()).then(p=>{latestPreviewId=p.preview_id;document.getElementById('submit-live-order').disabled=!p.can_submit_live_order;setActionResult('Preview '+p.safety_gate_result,p)})}function submitLiveOrder(){postJson('/api/live/order/submit',{...livePayload(),preview_id:latestPreviewId,typed_confirmation:'CONFIRM_LIVE_ORDER',approval_mode:true}).then(p=>{document.getElementById('submit-live-order').disabled=true;setActionResult('Submit '+p.status,p)})}function enableKillSwitch(){postJson('/api/live/kill-switch',{}).then(p=>setActionResult('Kill switch enabled',p))}function resetKillSwitch(){postJson('/api/live/kill-switch/reset',{}).then(p=>setActionResult('Kill switch reset',p))}
function paperPayload(){return{symbol:(document.getElementById('paper-symbol').value||document.getElementById('market-symbol').value).trim().toUpperCase(),side:document.getElementById('paper-side').value,quantity:Number(document.getElementById('paper-qty').value),entry_price:Number(document.getElementById('paper-entry').value),stop_loss:Number(document.getElementById('paper-sl').value),target_1:Number(document.getElementById('paper-t1').value),target_2:Number(document.getElementById('paper-t2').value)}}function submitPaperOrder(){postJson('/api/paper/order',paperPayload()).then(p=>{document.getElementById('paper-order-result').textContent=JSON.stringify(p,null,2);loadPaperStatus()})}function addPaperBalance(){postJson('/api/paper/balance/add',{amount:Number(document.getElementById('paper-add-amount').value)}).then(p=>{document.getElementById('paper-order-result').textContent=JSON.stringify(p,null,2);loadPaperStatus()})}function resetPaperAccount(){postJson('/api/paper/reset',{}).then(p=>{document.getElementById('paper-order-result').textContent=JSON.stringify(p,null,2);loadPaperStatus()})}function closePaperPosition(id){postJson('/api/paper/position/close',{position_id:id}).then(p=>{document.getElementById('paper-order-result').textContent=JSON.stringify(p,null,2);loadPaperStatus()})}
function settingsPayload(){return{paper_auto_trade_enabled:document.getElementById('setting-auto').value==='true',sizing_mode:document.getElementById('setting-sizing').value,fixed_quantity:Number(document.getElementById('setting-fixed-qty').value),fixed_amount:Number(document.getElementById('setting-fixed-amount').value),target_mode:document.getElementById('setting-target-mode').value,target_value:Number(document.getElementById('setting-target-value').value),stop_loss_mode:document.getElementById('setting-sl-mode').value,stop_loss_value:Number(document.getElementById('setting-sl-value').value),max_open_positions:Number(document.getElementById('setting-max-open').value),max_trades_per_day:Number(document.getElementById('setting-max-trades').value),max_daily_loss:Number(document.getElementById('setting-max-loss').value)}}function loadPaperSettings(){fetch('/api/paper/settings?symbol='+encodeURIComponent(document.getElementById('market-symbol').value)).then(r=>r.json()).then(p=>{const s=p.settings||p;document.getElementById('setting-auto').value=String(!!s.paper_auto_trade_enabled);document.getElementById('setting-sizing').value=s.sizing_mode;document.getElementById('setting-fixed-qty').value=s.fixed_quantity;document.getElementById('setting-fixed-amount').value=s.fixed_amount;document.getElementById('setting-target-mode').value=s.target_mode;document.getElementById('setting-target-value').value=s.target_value;document.getElementById('setting-sl-mode').value=s.stop_loss_mode;document.getElementById('setting-sl-value').value=s.stop_loss_value;document.getElementById('setting-max-open').value=s.max_open_positions;document.getElementById('setting-max-trades').value=s.max_trades_per_day;document.getElementById('setting-max-loss').value=s.max_daily_loss;renderKv('paper-auto-preview',p.auto_trade_preview||{},['selected_symbol','latest_ltp','state','sizing_mode','fixed_amount','fixed_quantity','calculated_quantity','entry_price','generated_stop_loss','generated_target_1','generated_target_2','block_reasons']);document.getElementById('paper-settings-raw').textContent=JSON.stringify(p,null,2)})}function savePaperSettings(){postJson('/api/paper/settings',settingsPayload()).then(p=>{document.getElementById('paper-settings-raw').textContent=JSON.stringify(p,null,2);loadPaperStatus();loadPaperSettings()})}
function loadPaperStatus(isAuto=false){fetch('/api/paper/status').then(r=>r.json()).then(p=>{renderKv('paper-summary',p.account_summary,['mode','cash_balance','equity','realized_pnl','unrealized_pnl','win_count','loss_count','win_rate','paper_auto_trade_state','go_live_allowed']);document.getElementById('paper-open-positions').innerHTML=(p.open_positions||[]).map(pos=>`<div class="paper-row"><strong>${pos.symbol} ${pos.side} x${pos.quantity}</strong><br>Entry ${pos.entry_price} · LTP ${pos.last_price??'DATA_UNAVAILABLE'} · P&L <span class="${Number(pos.unrealized_pnl||0)>=0?'profit':'loss'}">${pos.unrealized_pnl}</span><br>SL ${pos.stop_loss} · T1 ${pos.target_1} · T2 ${pos.target_2}<br><button onclick="closePaperPosition('${pos.position_id}')">Manual Exit</button></div>`).join('')||'No open paper positions.';document.getElementById('paper-closed-trades').innerHTML=(p.closed_trades||[]).slice(-10).reverse().map(t=>`<div class="paper-row"><strong>${t.symbol} ${t.exit_reason}</strong><br>Entry ${t.entry_price} → Exit ${t.exit_price} · P&L <span class="${Number(t.pnl||0)>=0?'profit':'loss'}">${t.pnl}</span></div>`).join('')||'No closed paper trades.';document.getElementById('paper-ledger').innerHTML=(p.statement_ledger||[]).slice(-10).reverse().map(e=>`<div class="paper-row"><strong>${e.event}</strong><br>${e.timestamp}<br>${e.message}</div>`).join('')||'No ledger entries yet.';if(!isAuto)document.getElementById('paper-raw').textContent=JSON.stringify(p,null,2)})}
function loadShadowStatus(){fetch('/api/shadow/status').then(r=>r.json()).then(p=>{renderKv('shadow-status',p,['mode','zerodha_status','data_source','paper_orders','fills','realized_pnl','unrealized_pnl','total_equity','go_live_allowed']);document.getElementById('shadow-raw').textContent=JSON.stringify(p,null,2)})}
fetch('/api/market/symbols?q=').then(r=>r.json()).then(p=>{marketSymbols=p.symbols||marketSymbols;renderWatchlist({symbols:marketSymbols})}).catch(()=>renderWatchlist({symbols:marketSymbols}));refreshMarketData();loadChart();loadLiveSignal();loadPaperStatus();loadPaperSettings();loadLiveReadiness();loadShadowStatus();startAutoRefresh();
</script></body></html>
"""


@dataclass(frozen=True)
class LiveOrderPreviewState:
    preview_id: str
    idempotency_key: str
    symbol: str
    exchange: str
    side: str
    quantity: int
    order_type: str
    product: str
    price: float
    safety_gate_result: str
    can_submit_live_order: bool
    block_reasons: tuple[str, ...]
    go_live_allowed: bool = False


_KILL_SWITCH_ENABLED = False
_PREVIEWS: dict[str, LiveOrderPreviewState] = {}
_SUBMITTED_IDEMPOTENCY_KEYS: set[str] = set()
_LAST_QUOTES: dict[str, dict[str, Any]] = {}
_PAPER_STARTING_BALANCE = 100_000.0
_PAPER: dict[str, Any] = {}
_PAPER_SETTINGS_DEFAULTS = {
    "paper_auto_trade_enabled": False,
    "sizing_mode": "FIXED_QUANTITY",
    "fixed_quantity": 1,
    "fixed_amount": 1000.0,
    "target_mode": "PERCENT",
    "target_value": 1.0,
    "stop_loss_mode": "PERCENT",
    "stop_loss_value": 0.5,
    "max_open_positions": 1,
    "max_trades_per_day": 5,
    "max_daily_loss": 1000.0,
    "go_live_allowed": False,
}
_PAPER_SETTINGS: dict[str, Any] = dict(_PAPER_SETTINGS_DEFAULTS)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _paper_ledger(event: str, message: str, **extra: Any) -> None:
    _PAPER.setdefault("statement_ledger", []).append({"event": event, "message": message, "timestamp": _now(), "data_source": "PAPER_TRADING_SIMULATOR", **extra})


def _reset_paper_state(starting_balance: float = _PAPER_STARTING_BALANCE) -> None:
    _PAPER.clear()
    _PAPER.update({"starting_balance": float(starting_balance), "cash_balance": float(starting_balance), "open_positions": [], "closed_trades": [], "statement_ledger": [], "paper_auto_trade_enabled": False, "paper_auto_trade_state": "OFF"})
    _paper_ledger("ACCOUNT_RESET", f"Virtual paper account reset to {starting_balance:.2f}")


_reset_paper_state()


class AlphaGateXRequestHandler(BaseHTTPRequestHandler):
    """HTTP handler exposing ALPHA-GATE X dashboard and JSON endpoints."""

    server_version = "AlphaGateXTradingTerminal/2.2"

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        if path == "/":
            self._send(200, HTML, "text/html; charset=utf-8")
        elif path == "/health":
            self._send_json(200, {"status": "ok", "service": "alpha-gate-x-shadow-trading-platform"})
        elif path == "/api/status":
            self._send_json(200, {"active_scope": "live_market_signal_paper_trading", "go_live_allowed": False})
        elif path == "/api/demo":
            self._send_json(200, {"mode": "UI_PREVIEW_ONLY", "go_live_allowed": False, "phases": [phase.as_dict() for phase in AegisQuantPlatform().run(_demo_bars())]})
        elif path == "/api/shadow/status":
            self._send_json(200, _shadow_status())
        elif path == "/api/live/readiness":
            self._send_json(200, _live_readiness())
        elif path == "/api/live/orders":
            self._send_json(200, _live_orders())
        elif path == "/api/safety/gates":
            self._send_json(200, _safety_gates())
        elif path == "/api/market/symbols":
            self._send_json(200, _market_symbols((query.get("q") or [""])[0]))
        elif path == "/api/market/watchlist":
            self._send_json(200, _market_watchlist())
        elif path == "/api/market/quote":
            self._send_json(200, _market_quote(_query_symbol(query)))
        elif path == "/api/market/history":
            self._send_json(200, _market_history(_query_symbol(query), interval=_query_interval(query)))
        elif path == "/api/signal/live":
            self._send_json(200, _live_signal(_query_symbol(query), auto_requested=_query_bool(query, "auto_trade")))
        elif path == "/api/signal/accuracy-report":
            self._send_json(200, _signal_accuracy_report(_query_symbol(query)))
        elif path == "/api/paper/status":
            self._send_json(200, _paper_status())
        elif path == "/api/paper/statement":
            self._send_json(200, _paper_statement())
        elif path == "/api/paper/settings":
            self._send_json(200, _paper_settings_response(_query_symbol(query)))
        else:
            self._send_json(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        payload = self._read_json_body()
        if path == "/api/live/order/preview":
            self._send_json(200, _live_order_preview(payload))
        elif path == "/api/live/order/submit":
            self._send_json(200, _live_order_submit(payload))
        elif path == "/api/live/kill-switch":
            self._send_json(200, _set_kill_switch(True))
        elif path == "/api/live/kill-switch/reset":
            self._send_json(200, _set_kill_switch(False))
        elif path == "/api/paper/balance/add":
            self._send_json(200, _paper_balance_add(payload))
        elif path == "/api/paper/reset":
            self._send_json(200, _paper_reset(payload))
        elif path == "/api/paper/order":
            self._send_json(200, _paper_order(payload))
        elif path == "/api/paper/position/close":
            self._send_json(200, _paper_position_close(payload))
        elif path == "/api/paper/auto-trade/toggle":
            self._send_json(200, _paper_auto_trade_toggle(payload))
        elif path == "/api/paper/settings":
            self._send_json(200, _paper_settings_update(payload))
        else:
            self._send_json(404, {"error": "not_found"})

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        """Silence default stderr logging."""

    def _read_json_body(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0:
            return {}
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
            return data if isinstance(data, dict) else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {}

    def _send_json(self, status: int, payload: Mapping[str, Any]) -> None:
        self._send(status, json.dumps(payload, indent=2), "application/json; charset=utf-8")

    def _send(self, status: int, body: str, content_type: str) -> None:
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def run(host: str = "127.0.0.1", port: int = 8080) -> None:
    ThreadingHTTPServer((host, port), AlphaGateXRequestHandler).serve_forever()


def _shadow_status() -> dict[str, Any]:
    audit_store = InMemoryAuditStore()
    engine = LivePaperTradingEngine(config=RuntimeConfig(), audit_store=audit_store)
    report = engine.build_report()
    shadow = ShadowRunValidator(audit_store).status()
    paper = _paper_status()["account_summary"]
    return {"mode": engine.config.trading_mode.value, "go_live_allowed": False, "zerodha_status": "READ_ONLY_READY" if os.environ.get("ZERODHA_API_KEY") and os.environ.get("ZERODHA_ACCESS_TOKEN") else "ZERODHA_UNAVAILABLE", "data_source": "RUNTIME_AUDIT_STORE", "signals_generated": report.signals_generated, "paper_orders": len(_PAPER.get("open_positions", [])) + len(_PAPER.get("closed_trades", [])), "fills": len(_PAPER.get("closed_trades", [])), "realized_pnl": paper["realized_pnl"], "unrealized_pnl": paper["unrealized_pnl"], "total_equity": paper["equity"], "shadow_days_completed": shadow.trading_days_completed, "shadow_recommendation": shadow.recommendation.value, "failure_reasons": tuple(shadow.failure_reasons), "ticker_wrapper_available": ReadOnlyKiteTickerWrapper is not None}


def _live_readiness() -> dict[str, Any]:
    env = os.environ
    instrument_path = env.get("ZERODHA_INSTRUMENT_DUMP_PATH", "data/instruments.csv").strip() or "data/instruments.csv"
    expected_user_id = env.get("ZERODHA_EXPECTED_USER_ID", "").strip()
    actual_user_id = env.get("ZERODHA_USER_ID", expected_user_id).strip()
    readiness = {"mode": "LIVE_MANUAL_APPROVAL_ONLY", "zerodha_credentials_visible": bool(env.get("ZERODHA_API_KEY", "").strip() and env.get("ZERODHA_API_SECRET", "").strip()), "access_token_visible": bool(env.get("ZERODHA_ACCESS_TOKEN", "").strip()), "expected_user_id_match": not expected_user_id or expected_user_id == actual_user_id, "instruments_csv_exists": Path(instrument_path).exists() and Path(instrument_path).stat().st_size > 0, "live_trading_env_enabled": _env_true("LIVE_TRADING_ENABLED"), "manual_approval_required": _env_true("MANUAL_LIVE_APPROVAL_REQUIRED"), "kill_switch_status": "ENABLED" if _kill_switch_active() else "DISABLED", "go_live_allowed": False}
    readiness["block_reasons"] = _live_block_reasons(readiness)
    return readiness


def _live_order_preview(payload: Mapping[str, Any]) -> dict[str, Any]:
    readiness = _live_readiness()
    symbol = str(payload.get("symbol", "")).strip().upper()
    exchange = str(payload.get("exchange", "NSE")).strip().upper()
    side = str(payload.get("side", "BUY")).strip().upper()
    order_type = str(payload.get("order_type", "LIMIT")).strip().upper()
    product = str(payload.get("product", "MIS")).strip().upper()
    quantity = _safe_int(payload.get("quantity"), 0)
    price = _safe_float(payload.get("price"), 0.0)
    reasons = list(readiness["block_reasons"])
    if exchange != "NSE": reasons.append("only NSE exchange is allowed in manual live mode")
    if side not in {"BUY", "SELL"}: reasons.append("side must be BUY or SELL")
    if order_type != "LIMIT": reasons.append("only LIMIT orders are allowed")
    if product not in {"MIS", "CNC"}: reasons.append("product must be MIS or CNC")
    if quantity < 1: reasons.append("quantity must be at least 1")
    if quantity > _max_live_quantity(): reasons.append(f"quantity exceeds max allowed {_max_live_quantity()}")
    if price <= 0: reasons.append("limit price is required")
    if symbol not in _symbol_whitelist(): reasons.append("symbol is not in LIVE_SYMBOL_WHITELIST")
    margin_check = _live_margin_check(symbol, exchange, side, quantity, order_type, price, product)
    if margin_check["status"] != "PASS": reasons.append(margin_check["reason"])
    preview = LiveOrderPreviewState(f"preview-{uuid4()}", f"live-preview:{uuid4()}", symbol, exchange, side, quantity, order_type, product, price, "PASS" if not reasons else "BLOCKED", not reasons, tuple(dict.fromkeys(reasons)))
    _PREVIEWS[preview.preview_id] = preview
    result = asdict(preview)
    result["margin_check"] = margin_check
    return result


def _live_order_submit(payload: Mapping[str, Any]) -> dict[str, Any]:
    preview_id = str(payload.get("preview_id", "")).strip()
    typed_confirmation = str(payload.get("typed_confirmation", "")).strip()
    approval_mode = bool(payload.get("approval_mode", False))
    preview = _PREVIEWS.get(preview_id)
    reasons: list[str] = []
    if preview is None: reasons.append("preview_id not found or expired")
    if typed_confirmation != "CONFIRM_LIVE_ORDER": reasons.append("typed confirmation mismatch")
    if not approval_mode: reasons.append("approval_mode must be true")
    if not _env_true("REAL_BROKER_ORDER_SUBMIT_ENABLED"): reasons.append("REAL_BROKER_ORDER_SUBMIT_ENABLED is not true")
    if preview is not None and preview.idempotency_key in _SUBMITTED_IDEMPOTENCY_KEYS: reasons.append("idempotency key already used")
    if preview is not None and not preview.can_submit_live_order: reasons.extend(preview.block_reasons)
    if _kill_switch_active(): reasons.append("kill switch enabled")
    reasons.extend(_live_readiness()["block_reasons"])
    return {"status": "BLOCKED", "broker_order_id": None, "go_live_allowed": False, "block_reasons": tuple(dict.fromkeys(reasons or ["real live order submission is intentionally fail-closed"]))}


def _live_orders() -> dict[str, Any]:
    return {"status": DATA_UNAVAILABLE, "orders": (), "go_live_allowed": False, "reason": "Zerodha order fetch adapter is not attached in this runtime"}


def _safety_gates() -> dict[str, Any]:
    readiness = _live_readiness()
    return {"go_live_allowed": False, "automatic_live_trading": "DISABLED", "auto_trade_env_enabled": _env_true("AUTO_TRADE_ENABLED"), "manual_approval_required": readiness["manual_approval_required"], "kill_switch_status": readiness["kill_switch_status"], "order_type_allowed": "LIMIT_ONLY", "default_quantity": 1, "block_reasons": readiness["block_reasons"]}


def _market_symbols(q: str = "") -> dict[str, Any]:
    query = (q or "").strip().upper()
    fallback = list(FALLBACK_SYMBOLS)
    if not query:
        return {"symbols": tuple(fallback[:50]), "count": min(len(fallback), 50), "query": query, "data_source": "FALLBACK_SYMBOL_UNIVERSE_EMPTY_QUERY", "validation_status": "VALIDATED", "go_live_allowed": False}

    def is_clean_symbol(symbol: str, instrument_type: str = "EQ") -> bool:
        symbol = (symbol or "").strip().upper()
        instrument_type = (instrument_type or "EQ").strip().upper()
        if symbol in {"NIFTY", "BANKNIFTY", "FINNIFTY"}:
            return True
        if instrument_type != "EQ":
            return False
        if symbol.endswith(("-NO", "-SG", "-TB", "-BE", "-BZ", "-SM", "-ST", "-RR")):
            return False
        if " " in symbol or len(symbol) > 20:
            return False
        return all(ch.isalnum() or ch in {"&", "-"} for ch in symbol)

    symbols: list[str] = []
    data_source = "FALLBACK_SYMBOL_UNIVERSE"
    path = Path(os.environ.get("ZERODHA_INSTRUMENT_DUMP_PATH", "data/instruments.csv").strip() or "data/instruments.csv")
    if path.exists() and path.stat().st_size > 0:
        try:
            with path.open(newline="", encoding="utf-8") as handle:
                for row in csv.DictReader(handle):
                    if row.get("exchange", "").upper() != "NSE":
                        continue
                    symbol = row.get("tradingsymbol", "").strip().upper()
                    instrument_type = row.get("instrument_type", "EQ").strip().upper()
                    if query not in symbol or not is_clean_symbol(symbol, instrument_type):
                        continue
                    if symbol not in symbols:
                        symbols.append(symbol)
                    if len(symbols) >= 50:
                        break
            if symbols:
                data_source = "ZERODHA_INSTRUMENT_DUMP_FILTERED"
        except Exception:
            symbols = []
            data_source = "FALLBACK_SYMBOL_UNIVERSE_CSV_READ_FAILED"
    for symbol in fallback:
        if query in symbol and symbol not in symbols:
            symbols.append(symbol)
        if len(symbols) >= 50:
            break
    return {"symbols": tuple(symbols[:50]), "count": len(symbols[:50]), "query": query, "data_source": data_source, "validation_status": "VALIDATED" if symbols else DATA_UNAVAILABLE, "go_live_allowed": False}


def _market_watchlist() -> dict[str, Any]:
    client, reason = _kite_client_from_env()
    symbols = tuple(FALLBACK_SYMBOLS[:12])
    return {"symbols": symbols, "data_source": "ZERODHA_KITE_READY" if client is not None else DATA_UNAVAILABLE, "validation_status": "READY" if client is not None else DATA_UNAVAILABLE, "connection_status": "ZERODHA_READY_FOR_QUOTE" if client is not None else reason, "go_live_allowed": False}


def _market_quote(symbol: str) -> dict[str, Any]:
    normalized = symbol.strip().upper() or "RELIANCE"
    cached = _LAST_QUOTES.get(normalized)
    if cached and cached.get("data_source") == "TEST_QUOTE" and cached.get("validation_status") == "VALIDATED":
        if isinstance(cached.get("ltp"), (int, float)):
            _paper_evaluate_positions(normalized, float(cached["ltp"]), "TEST_QUOTE")
        return cached
    client, reason = _kite_client_from_env()
    if client is None:
        return _unavailable_quote(normalized, reason)
    instrument_key = _kite_instrument_key(normalized)
    try:
        quote = client.quote([instrument_key])
        row = quote.get(instrument_key) or {}
        if not row:
            return _unavailable_quote(normalized, "ZERODHA_QUOTE_EMPTY")
        ohlc = row.get("ohlc") or {}
        last_price = row.get("last_price", DATA_UNAVAILABLE)
        close = ohlc.get("close", DATA_UNAVAILABLE)
        change_percent: float | str = DATA_UNAVAILABLE
        if isinstance(last_price, (int, float)) and isinstance(close, (int, float)) and close:
            change_percent = round(((last_price - close) / close) * 100, 2)
        payload = {"symbol": normalized, "instrument_key": instrument_key, "ltp": last_price, "open": ohlc.get("open", DATA_UNAVAILABLE), "high": ohlc.get("high", DATA_UNAVAILABLE), "low": ohlc.get("low", DATA_UNAVAILABLE), "close": close, "change_percent": change_percent, "volume": row.get("volume", DATA_UNAVAILABLE), "last_update": _as_text(row.get("last_trade_time") or row.get("timestamp")), "data_source": "ZERODHA_KITE_QUOTE", "validation_status": "VALIDATED", "connection_status": "ZERODHA_READ_ONLY_CONNECTED", "go_live_allowed": False}
        _LAST_QUOTES[normalized] = payload
        if isinstance(last_price, (int, float)):
            _paper_evaluate_positions(normalized, float(last_price), "ZERODHA_KITE_QUOTE")
        return payload
    except Exception as exc:
        return _unavailable_quote(normalized, f"ZERODHA_QUOTE_API_UNAVAILABLE:{exc.__class__.__name__}")


def _market_history(symbol: str, *, interval: str = "5minute") -> dict[str, Any]:
    normalized = symbol.strip().upper() or "RELIANCE"
    client, reason = _kite_client_from_env()
    if client is None:
        return _unavailable_history(normalized, reason, interval)
    token, token_reason = _instrument_token_for_symbol(normalized)
    if token is None:
        return _unavailable_history(normalized, token_reason, interval)
    to_date = datetime.now(UTC)
    from_date = to_date - timedelta(days=30 if interval == "60minute" else 10)
    try:
        rows = client.historical_data(token, from_date, to_date, interval)
        candles = tuple({"timestamp": _as_text(row.get("date")), "open": row.get("open"), "high": row.get("high"), "low": row.get("low"), "close": row.get("close"), "volume": row.get("volume")} for row in rows if isinstance(row, Mapping))
        if not candles:
            return _unavailable_history(normalized, "ZERODHA_HISTORY_EMPTY", interval)
        return {"symbol": normalized, "instrument_token": token, "interval": interval, "candles": candles, "data_source": "ZERODHA_KITE_HISTORICAL", "validation_status": "VALIDATED", "connection_status": "ZERODHA_READ_ONLY_CONNECTED", "go_live_allowed": False}
    except Exception as exc:
        return _unavailable_history(normalized, f"ZERODHA_HISTORY_API_UNAVAILABLE:{exc.__class__.__name__}", interval)


def _live_signal(symbol: str, *, auto_requested: bool = False) -> dict[str, Any]:
    history = _market_history(symbol, interval="5minute")
    if history.get("validation_status") != "VALIDATED":
        return _signal_unavailable(symbol, str(history.get("connection_status", DATA_UNAVAILABLE)), auto_requested=auto_requested)
    candles = history.get("candles", ())
    if not isinstance(candles, (tuple, list)) or len(candles) < 21:
        return _signal_unavailable(symbol, "INSUFFICIENT_CANDLES", auto_requested=auto_requested)
    signal = _signal_from_candles(str(history.get("symbol", symbol)).upper(), candles, data_source=str(history.get("data_source", "ZERODHA_KITE_HISTORICAL")))
    signal["auto_trade_state"] = _auto_trade_state(signal, auto_requested=auto_requested)
    _paper_auto_trade_from_signal(signal)
    return signal


def _signal_from_candles(symbol: str, candles: Any, confirmation_candles: Any | None = None, trend_candles: Any | None = None, *, data_source: str = "ZERODHA_KITE_HISTORICAL") -> dict[str, Any]:
    signal = _strict_signal_from_candles(symbol, candles, confirmation_candles or candles, trend_candles or confirmation_candles or candles, data_source=data_source)
    signal["auto_trade_state"] = _auto_trade_state(signal, auto_requested=False)
    return signal


def _signal_unavailable(symbol: str, reason: str, *, auto_requested: bool) -> dict[str, Any]:
    payload = _strict_signal_unavailable(symbol, reason)
    payload["auto_trade_state"] = _auto_trade_state(payload, auto_requested=auto_requested)
    return payload


def _signal_accuracy_report(symbol: str) -> dict[str, Any]:
    return _strict_accuracy_report(symbol, ())


def _auto_trade_state(signal: Mapping[str, Any], *, auto_requested: bool) -> dict[str, Any]:
    reasons: list[str] = []
    if not auto_requested: reasons.append("AUTO_TRADE_TOGGLE_OFF")
    if not _env_true("AUTO_TRADE_ENABLED"): reasons.append("AUTO_TRADE_ENABLED is not true")
    if not _env_true("REAL_BROKER_ORDER_SUBMIT_ENABLED"): reasons.append("REAL_BROKER_ORDER_SUBMIT_ENABLED is not true")
    if _kill_switch_active(): reasons.append("kill switch enabled")
    reasons.extend(_live_readiness()["block_reasons"])
    decision = str(signal.get("decision", DATA_UNAVAILABLE))
    confidence = _safe_float(signal.get("confidence_score"), 0.0)
    risk_reward = _safe_float(signal.get("risk_reward"), 0.0)
    if decision not in {"BUY", "SELL"}: reasons.append("signal decision is not BUY/SELL")
    if confidence < 70: reasons.append("confidence_score below 70")
    if risk_reward < 2: reasons.append("risk_reward below 2")
    eligible = not reasons
    return {"requested": auto_requested, "state": "ARMED" if eligible else "BLOCKED" if auto_requested else "DISABLED", "eligible": eligible, "reason": "PASS" if eligible else "; ".join(dict.fromkeys(reasons)), "go_live_allowed": False}


def _paper_settings_response(symbol: str = "RELIANCE") -> dict[str, Any]:
    return {"settings": dict(_PAPER_SETTINGS), "auto_trade_preview": _paper_auto_trade_plan(symbol, None), "validation_status": "VALIDATED", "go_live_allowed": False}


def _paper_settings_update(payload: Mapping[str, Any]) -> dict[str, Any]:
    if "paper_auto_trade_enabled" in payload:
        _PAPER_SETTINGS["paper_auto_trade_enabled"] = bool(payload.get("paper_auto_trade_enabled"))
    if "enabled" in payload:
        _PAPER_SETTINGS["paper_auto_trade_enabled"] = bool(payload.get("enabled"))
    sizing_mode = str(payload.get("sizing_mode", _PAPER_SETTINGS["sizing_mode"])).upper()
    if sizing_mode in {"FIXED_QUANTITY", "FIXED_AMOUNT"}: _PAPER_SETTINGS["sizing_mode"] = sizing_mode
    target_mode = str(payload.get("target_mode", _PAPER_SETTINGS["target_mode"])).upper()
    if target_mode in {"PERCENT", "POINTS"}: _PAPER_SETTINGS["target_mode"] = target_mode
    stop_loss_mode = str(payload.get("stop_loss_mode", _PAPER_SETTINGS["stop_loss_mode"])).upper()
    if stop_loss_mode in {"PERCENT", "POINTS"}: _PAPER_SETTINGS["stop_loss_mode"] = stop_loss_mode
    _PAPER_SETTINGS["fixed_quantity"] = max(1, _safe_int(payload.get("fixed_quantity", _PAPER_SETTINGS["fixed_quantity"]), 1))
    _PAPER_SETTINGS["fixed_amount"] = max(0.0, _safe_float(payload.get("fixed_amount", _PAPER_SETTINGS["fixed_amount"]), 1000.0))
    _PAPER_SETTINGS["target_value"] = max(0.0, _safe_float(payload.get("target_value", _PAPER_SETTINGS["target_value"]), 1.0))
    _PAPER_SETTINGS["stop_loss_value"] = max(0.0, _safe_float(payload.get("stop_loss_value", _PAPER_SETTINGS["stop_loss_value"]), 0.5))
    _PAPER_SETTINGS["max_open_positions"] = max(1, _safe_int(payload.get("max_open_positions", _PAPER_SETTINGS["max_open_positions"]), 1))
    _PAPER_SETTINGS["max_trades_per_day"] = max(1, _safe_int(payload.get("max_trades_per_day", _PAPER_SETTINGS["max_trades_per_day"]), 5))
    _PAPER_SETTINGS["max_daily_loss"] = max(0.0, _safe_float(payload.get("max_daily_loss", _PAPER_SETTINGS["max_daily_loss"]), 1000.0))
    _PAPER["paper_auto_trade_enabled"] = bool(_PAPER_SETTINGS["paper_auto_trade_enabled"])
    _PAPER["paper_auto_trade_state"] = "ARMED" if _PAPER["paper_auto_trade_enabled"] and not _kill_switch_active() else "OFF" if not _PAPER["paper_auto_trade_enabled"] else "BLOCKED"
    _paper_ledger("PAPER_SETTINGS_UPDATE", "Paper auto-trade settings updated", settings=dict(_PAPER_SETTINGS))
    response = _paper_settings_response()
    response["status"] = "PASS"
    return response


def _paper_auto_trade_plan(symbol: str, signal: Mapping[str, Any] | None) -> dict[str, Any]:
    symbol = (symbol or "RELIANCE").upper()
    settings = _PAPER_SETTINGS
    quote = _LAST_QUOTES.get(symbol)
    entry = float(quote["ltp"]) if quote and quote.get("validation_status") == "VALIDATED" and isinstance(quote.get("ltp"), (int, float)) else 0.0
    quantity = int(settings["fixed_quantity"]) if settings["sizing_mode"] == "FIXED_QUANTITY" else int(float(settings["fixed_amount"]) // entry) if entry > 0 else 0
    target_1, target_2, stop_loss = _paper_generated_exits(entry)
    reasons: list[str] = []
    if not settings["paper_auto_trade_enabled"]: reasons.append("PAPER_AUTO_TRADE_OFF")
    if signal is not None:
        if signal.get("decision") != "BUY": reasons.append("SIGNAL_NOT_BUY")
        if signal.get("validation_status") != "VALIDATED": reasons.append("SIGNAL_NOT_VALIDATED")
        if _safe_float(signal.get("confidence_score"), 0.0) < 75: reasons.append("CONFIDENCE_BELOW_75")
        if _safe_float(signal.get("risk_reward"), 0.0) < 2: reasons.append("RISK_REWARD_BELOW_2")
    if quote is None or quote.get("validation_status") != "VALIDATED": reasons.append("VALIDATED_QUOTE_UNAVAILABLE")
    if _kill_switch_active(): reasons.append("KILL_SWITCH_ENABLED")
    if len(_PAPER.get("open_positions", [])) >= int(settings["max_open_positions"]): reasons.append("MAX_OPEN_POSITIONS_REACHED")
    if _paper_trades_today() >= int(settings["max_trades_per_day"]): reasons.append("MAX_TRADES_PER_DAY_REACHED")
    if _paper_daily_loss() >= float(settings["max_daily_loss"]): reasons.append("MAX_DAILY_LOSS_REACHED")
    if quantity < 1: reasons.append("INSUFFICIENT_PAPER_AMOUNT")
    if entry > 0 and quantity * entry > float(_PAPER.get("cash_balance", 0.0)): reasons.append("INSUFFICIENT_PAPER_BALANCE")
    if any(p["symbol"] == symbol and p["side"] == "BUY" for p in _PAPER.get("open_positions", [])):
        reasons.append("AUTO_SCALE_IN_OFF")
        reasons.append("DUPLICATE_OPEN_POSITION")
    state = "ARMED" if not reasons else "OFF" if reasons == ["PAPER_AUTO_TRADE_OFF"] else "BLOCKED"
    return {"requested": bool(settings["paper_auto_trade_enabled"]), "state": state, "selected_symbol": symbol, "latest_ltp": round(entry, 2) if entry else DATA_UNAVAILABLE, "sizing_mode": settings["sizing_mode"], "calculated_quantity": quantity, "fixed_amount": settings["fixed_amount"], "fixed_quantity": settings["fixed_quantity"], "entry_price": round(entry, 2) if entry else DATA_UNAVAILABLE, "generated_stop_loss": stop_loss, "generated_target_1": target_1, "generated_target_2": target_2, "block_reasons": tuple(dict.fromkeys(reasons)), "go_live_allowed": False}


def _paper_generated_exits(entry: float) -> tuple[float | str, float | str, float | str]:
    if entry <= 0: return DATA_UNAVAILABLE, DATA_UNAVAILABLE, DATA_UNAVAILABLE
    target_value = float(_PAPER_SETTINGS["target_value"]); stop_value = float(_PAPER_SETTINGS["stop_loss_value"])
    target_1 = entry + target_value if _PAPER_SETTINGS["target_mode"] == "POINTS" else entry * (1 + target_value / 100)
    target_2 = entry + target_value * 2 if _PAPER_SETTINGS["target_mode"] == "POINTS" else entry * (1 + target_value * 2 / 100)
    stop_loss = entry - stop_value if _PAPER_SETTINGS["stop_loss_mode"] == "POINTS" else entry * (1 - stop_value / 100)
    return round(target_1, 2), round(target_2, 2), round(stop_loss, 2)


def _paper_status() -> dict[str, Any]:
    _paper_mark_to_market()
    summary = _paper_summary()
    return {"account_summary": summary, "open_positions": tuple(_PAPER.get("open_positions", [])), "closed_trades": tuple(_PAPER.get("closed_trades", [])), "statement_ledger": tuple(_PAPER.get("statement_ledger", [])), "settings": dict(_PAPER_SETTINGS), "auto_trade_preview": _paper_auto_trade_plan("RELIANCE", None), "validation_status": "VALIDATED", "data_source": "PAPER_TRADING_SIMULATOR", "timestamp": _now(), "go_live_allowed": False}


def _paper_statement() -> dict[str, Any]:
    status = _paper_status()
    return {"account_summary": status["account_summary"], "open_positions": status["open_positions"], "closed_trades": status["closed_trades"], "ledger_entries": status["statement_ledger"], "realized_pnl": status["account_summary"]["realized_pnl"], "unrealized_pnl": status["account_summary"]["unrealized_pnl"], "win_rate": status["account_summary"]["win_rate"], "validation_status": "VALIDATED", "go_live_allowed": False}


def _paper_balance_add(payload: Mapping[str, Any]) -> dict[str, Any]:
    amount = _safe_float(payload.get("amount"), 0.0)
    if amount <= 0: return {"status": "BLOCKED", "reason": "amount must be positive", "go_live_allowed": False}
    _PAPER["cash_balance"] = round(float(_PAPER.get("cash_balance", 0.0)) + amount, 2)
    _PAPER["starting_balance"] = round(float(_PAPER.get("starting_balance", 0.0)) + amount, 2)
    _paper_ledger("BALANCE_ADD", f"Added virtual paper balance {amount:.2f}", amount=amount)
    return {"status": "PASS", "message": "virtual paper balance added", "paper_status": _paper_status(), "go_live_allowed": False}


def _paper_reset(payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
    starting = _safe_float((payload or {}).get("starting_balance"), _PAPER_STARTING_BALANCE)
    _reset_paper_state(starting if starting > 0 else _PAPER_STARTING_BALANCE)
    _PAPER_SETTINGS.clear(); _PAPER_SETTINGS.update(dict(_PAPER_SETTINGS_DEFAULTS))
    return {"status": "PASS", "message": "paper account reset", "paper_status": _paper_status(), "go_live_allowed": False}


def _paper_order(payload: Mapping[str, Any]) -> dict[str, Any]:
    symbol = str(payload.get("symbol", "RELIANCE")).strip().upper()
    side = str(payload.get("side", "BUY")).strip().upper()
    quantity = _safe_int(payload.get("quantity"), 0)
    if quantity <= 0:
        return {"status": "BLOCKED", "reason": "quantity must be positive", "go_live_allowed": False}
    price, source = _paper_execution_price(symbol, payload)
    if price <= 0:
        return {"status": "BLOCKED", "reason": "validated quote unavailable and entry_price missing", "go_live_allowed": False}
    if side == "BUY":
        return _paper_open_long(symbol, quantity, price, payload, source, event="PAPER_BUY")
    if side == "SELL":
        open_long = next((p for p in _PAPER.get("open_positions", []) if p["symbol"] == symbol and p["side"] == "BUY"), None)
        if open_long is None:
            return {"status": "BLOCKED", "reason": "SELL opens short only when explicitly supported; no matching long paper position found", "go_live_allowed": False}
        open_quantity = int(open_long["quantity"])
        if quantity > open_quantity:
            return {"status": "BLOCKED", "reason": "SELL_QUANTITY_EXCEEDS_OPEN_LONG", "requested_quantity": quantity, "open_quantity": open_quantity, "go_live_allowed": False}
        if quantity < open_quantity:
            return _paper_partial_close_long(open_long["position_id"], quantity, price, "MANUAL_PARTIAL_EXIT", source)
        return _paper_close_position(open_long["position_id"], price, "MANUAL_EXIT", source)
    return {"status": "BLOCKED", "reason": "side must be BUY or SELL", "go_live_allowed": False}


def _paper_partial_close_long(position_id: str, quantity: int, exit_price: float, exit_reason: str, source: str) -> dict[str, Any]:
    position = _paper_find_position(position_id)
    if position is None:
        return {"status": "BLOCKED", "reason": "position_id not found", "go_live_allowed": False}
    open_quantity = int(position["quantity"])
    if quantity <= 0 or quantity >= open_quantity:
        return {"status": "BLOCKED", "reason": "partial quantity must be between 1 and open quantity - 1", "go_live_allowed": False}
    entry = float(position["entry_price"])
    pnl = round((exit_price - entry) * quantity, 2)
    proceeds = round(exit_price * quantity, 2)
    remaining = open_quantity - quantity
    _PAPER["cash_balance"] = round(float(_PAPER.get("cash_balance", 0.0)) + proceeds, 2)
    position["quantity"] = remaining
    position["last_price"] = round(exit_price, 2)
    position["unrealized_pnl"] = round((exit_price - entry) * remaining, 2)
    partial_trade = {
        "position_id": position_id,
        "symbol": position["symbol"],
        "side": position["side"],
        "quantity": quantity,
        "entry_price": round(entry, 2),
        "exit_price": round(exit_price, 2),
        "exit_reason": exit_reason,
        "opened_at": position.get("opened_at"),
        "closed_at": _now(),
        "pnl": pnl,
        "data_source": source,
        "status": "PARTIALLY_CLOSED",
        "go_live_allowed": False,
    }
    _PAPER.setdefault("closed_trades", []).append(partial_trade)
    _paper_ledger(exit_reason, f"Partially closed virtual {position['symbol']} x{quantity} @ {exit_price:.2f}; P&L {pnl:.2f}", position_id=position_id, symbol=position["symbol"], quantity=quantity, pnl=pnl)
    return {"status": "PASS", "partial_trade": partial_trade, "paper_order": position, "paper_status": _paper_status(), "go_live_allowed": False}


def _paper_position_close(payload: Mapping[str, Any]) -> dict[str, Any]:
    position_id = str(payload.get("position_id", "")).strip(); position = _paper_find_position(position_id)
    if position is None: return {"status": "BLOCKED", "reason": "position_id not found", "go_live_allowed": False}
    price, source = _paper_execution_price(position["symbol"], payload)
    if price <= 0: price = float(position.get("entry_price", 0.0)); source = "PAPER_ENTRY_PRICE_FALLBACK"
    return _paper_close_position(position_id, price, "MANUAL_EXIT", source)


def _paper_auto_trade_toggle(payload: Mapping[str, Any]) -> dict[str, Any]:
    return _paper_settings_update({"paper_auto_trade_enabled": bool(payload.get("enabled", False))})


def _paper_open_long(symbol: str, quantity: int, price: float, payload: Mapping[str, Any], source: str, *, event: str) -> dict[str, Any]:
    cost = round(price * quantity, 2)
    if float(_PAPER.get("cash_balance", 0.0)) < cost:
        return {"status": "BLOCKED", "reason": "INSUFFICIENT_PAPER_BALANCE", "required_cash": cost, "cash_balance": _PAPER.get("cash_balance", 0.0), "go_live_allowed": False}

    existing = next((p for p in _PAPER.get("open_positions", []) if p["symbol"] == symbol and p["side"] == "BUY"), None)
    _PAPER["cash_balance"] = round(float(_PAPER.get("cash_balance", 0.0)) - cost, 2)

    if existing is not None:
        old_quantity = int(existing["quantity"])
        old_entry = float(existing["entry_price"])
        new_quantity = old_quantity + quantity
        average_price = round(((old_entry * old_quantity) + (price * quantity)) / new_quantity, 2)
        existing["quantity"] = new_quantity
        existing["entry_price"] = average_price
        existing["last_price"] = round(price, 2)
        existing["lot_count"] = int(existing.get("lot_count", 1)) + 1
        existing["unrealized_pnl"] = round((price - average_price) * new_quantity, 2)
        for key in ("stop_loss", "target_1", "target_2"):
            value = _safe_float(payload.get(key), 0.0)
            if value > 0:
                existing[key] = round(value, 2)
        _paper_ledger("PAPER_BUY_SCALE_IN", f"Added virtual BUY lot {quantity} {symbol} @ {price:.2f}; average {average_price:.2f}", position_id=existing["position_id"], symbol=symbol, quantity=quantity, price=price, average_price=average_price)
        return {"status": "PASS", "paper_order": existing, "paper_status": _paper_status(), "go_live_allowed": False}

    position = {
        "position_id": f"paper-{uuid4()}",
        "symbol": symbol,
        "side": "BUY",
        "quantity": quantity,
        "entry_price": round(price, 2),
        "stop_loss": round(_safe_float(payload.get("stop_loss"), 0.0), 2),
        "target_1": round(_safe_float(payload.get("target_1"), 0.0), 2),
        "target_2": round(_safe_float(payload.get("target_2"), 0.0), 2),
        "opened_at": _now(),
        "data_source": source,
        "status": "OPEN",
        "last_price": round(price, 2),
        "unrealized_pnl": 0.0,
        "lot_count": 1,
        "go_live_allowed": False,
    }
    _PAPER.setdefault("open_positions", []).append(position)
    _paper_ledger(event, f"Opened virtual BUY {quantity} {symbol} @ {price:.2f}", position_id=position["position_id"], symbol=symbol, quantity=quantity, price=price)
    return {"status": "PASS", "paper_order": position, "paper_status": _paper_status(), "go_live_allowed": False}


def _paper_close_position(position_id: str, exit_price: float, exit_reason: str, source: str) -> dict[str, Any]:
    position = _paper_find_position(position_id)
    if position is None: return {"status": "BLOCKED", "reason": "position_id not found", "go_live_allowed": False}
    qty = int(position["quantity"]); entry = float(position["entry_price"]); pnl = round((exit_price - entry) * qty, 2); proceeds = round(exit_price * qty, 2)
    _PAPER["cash_balance"] = round(float(_PAPER.get("cash_balance", 0.0)) + proceeds, 2)
    _PAPER["open_positions"] = [p for p in _PAPER.get("open_positions", []) if p["position_id"] != position_id]
    trade = {**position, "status": "CLOSED", "exit_price": round(exit_price, 2), "exit_reason": exit_reason, "closed_at": _now(), "pnl": pnl, "data_source": source, "go_live_allowed": False}
    _PAPER.setdefault("closed_trades", []).append(trade)
    _paper_ledger(exit_reason, f"Closed virtual {position['symbol']} @ {exit_price:.2f}; P&L {pnl:.2f}", position_id=position_id, symbol=position["symbol"], pnl=pnl)
    return {"status": "PASS", "closed_trade": trade, "paper_status": _paper_status(), "go_live_allowed": False}


def _paper_evaluate_positions(symbol: str, last_price: float, source: str) -> None:
    for position in list(_PAPER.get("open_positions", [])):
        if position["symbol"] != symbol or position["side"] != "BUY": continue
        position["last_price"] = round(last_price, 2); position["unrealized_pnl"] = round((last_price - float(position["entry_price"])) * int(position["quantity"]), 2)
        stop_loss = float(position.get("stop_loss") or 0.0); target_1 = float(position.get("target_1") or 0.0); target_2 = float(position.get("target_2") or 0.0)
        if stop_loss > 0 and last_price <= stop_loss: _paper_close_position(position["position_id"], last_price, "STOP_LOSS_HIT", source)
        elif target_2 > 0 and last_price >= target_2: _paper_close_position(position["position_id"], last_price, "TARGET_2_HIT", source)
        elif target_1 > 0 and last_price >= target_1: _paper_close_position(position["position_id"], last_price, "TARGET_1_HIT", source)


def _paper_auto_trade_from_signal(signal: Mapping[str, Any]) -> None:
    symbol = str(signal.get("symbol", "")).upper(); plan = _paper_auto_trade_plan(symbol, signal); _PAPER["paper_auto_trade_state"] = plan["state"]
    if plan["state"] != "ARMED": return
    payload = {"stop_loss": plan["generated_stop_loss"], "target_1": plan["generated_target_1"], "target_2": plan["generated_target_2"]}
    _paper_open_long(symbol, int(plan["calculated_quantity"]), float(plan["entry_price"]), payload, "PAPER_AUTO_TRADE_FROM_SIGNAL", event="PAPER_AUTO_BUY")


def _paper_mark_to_market() -> None:
    for position in _PAPER.get("open_positions", []):
        quote = _LAST_QUOTES.get(position["symbol"])
        if quote and isinstance(quote.get("ltp"), (int, float)):
            last = float(quote["ltp"]); position["last_price"] = round(last, 2); position["unrealized_pnl"] = round((last - float(position["entry_price"])) * int(position["quantity"]), 2)


def _paper_summary() -> dict[str, Any]:
    open_positions = _PAPER.get("open_positions", []); closed = _PAPER.get("closed_trades", [])
    unrealized = round(sum(float(p.get("unrealized_pnl", 0.0)) for p in open_positions), 2); realized = round(sum(float(t.get("pnl", 0.0)) for t in closed), 2)
    open_value = round(sum(float(p.get("last_price", p.get("entry_price", 0.0))) * int(p.get("quantity", 0)) for p in open_positions), 2)
    equity = round(float(_PAPER.get("cash_balance", 0.0)) + open_value, 2)
    wins = sum(1 for t in closed if float(t.get("pnl", 0.0)) > 0); losses = sum(1 for t in closed if float(t.get("pnl", 0.0)) <= 0); total = wins + losses
    return {"mode": "PAPER_TRADING_ONLY", "starting_balance": round(float(_PAPER.get("starting_balance", 0.0)), 2), "cash_balance": round(float(_PAPER.get("cash_balance", 0.0)), 2), "equity": equity, "realized_pnl": realized, "unrealized_pnl": unrealized, "open_position_count": len(open_positions), "closed_trade_count": len(closed), "win_count": wins, "loss_count": losses, "win_rate": round((wins / total) * 100, 2) if total else DATA_UNAVAILABLE, "paper_auto_trade_state": _PAPER.get("paper_auto_trade_state", "OFF"), "validation_status": "VALIDATED", "go_live_allowed": False}


def _paper_execution_price(symbol: str, payload: Mapping[str, Any]) -> tuple[float, str]:
    entered = _safe_float(payload.get("limit_price") or payload.get("entry_price") or payload.get("price"), 0.0)
    if entered > 0:
        return entered, "USER_ENTERED_PAPER_PRICE"
    quote = _LAST_QUOTES.get(symbol)
    if quote and quote.get("validation_status") == "VALIDATED" and isinstance(quote.get("ltp"), (int, float)):
        return float(quote["ltp"]), "ZERODHA_KITE_QUOTE" if quote.get("data_source") != "TEST_QUOTE" else "TEST_QUOTE"
    return 0.0, DATA_UNAVAILABLE


def _paper_find_position(position_id: str) -> dict[str, Any] | None:
    return next((p for p in _PAPER.get("open_positions", []) if p["position_id"] == position_id), None)


def _paper_trades_today() -> int:
    today = datetime.now(UTC).date().isoformat()
    return sum(1 for trade in _PAPER.get("closed_trades", []) if str(trade.get("closed_at", "")).startswith(today)) + sum(1 for position in _PAPER.get("open_positions", []) if str(position.get("opened_at", "")).startswith(today))


def _paper_daily_loss() -> float:
    today = datetime.now(UTC).date().isoformat()
    return round(abs(sum(float(trade.get("pnl", 0.0)) for trade in _PAPER.get("closed_trades", []) if str(trade.get("closed_at", "")).startswith(today) and float(trade.get("pnl", 0.0)) < 0)), 2)


def _live_margin_check(symbol: str, exchange: str, side: str, quantity: int, order_type: str, price: float, product: str) -> dict[str, Any]:
    client, reason = _kite_client_from_env()
    if client is None: return {"status": "BLOCKED", "reason": reason, "required_margin": DATA_UNAVAILABLE, "available_margin": DATA_UNAVAILABLE, "go_live_allowed": False}
    try:
        if not hasattr(client, "order_margins"): return {"status": "BLOCKED", "reason": "KITE_ORDER_MARGINS_METHOD_UNAVAILABLE", "go_live_allowed": False}
        margin_response = client.order_margins([{"exchange": exchange, "tradingsymbol": symbol, "transaction_type": side, "variety": "regular", "product": product, "order_type": order_type, "quantity": quantity, "price": price}])
        margin_row = margin_response[0] if isinstance(margin_response, list) and margin_response else margin_response
        required_margin = _extract_required_margin(margin_row); available_margin = _extract_available_margin(client.margins())
        if required_margin is None: return {"status": "BLOCKED", "reason": "REQUIRED_MARGIN_UNAVAILABLE", "go_live_allowed": False}
        if available_margin is None: return {"status": "BLOCKED", "reason": "AVAILABLE_MARGIN_UNAVAILABLE", "required_margin": required_margin, "go_live_allowed": False}
        if available_margin < required_margin: return {"status": "BLOCKED", "reason": "INSUFFICIENT_AVAILABLE_MARGIN", "required_margin": required_margin, "available_margin": available_margin, "go_live_allowed": False}
        return {"status": "PASS", "reason": "MARGIN_CHECK_PASS", "required_margin": required_margin, "available_margin": available_margin, "go_live_allowed": False}
    except Exception as exc:
        return {"status": "BLOCKED", "reason": f"MARGIN_API_UNAVAILABLE:{exc.__class__.__name__}", "go_live_allowed": False}


def _extract_required_margin(payload: Any) -> float | None:
    for path in (("total",), ("final", "total"), ("initial", "total"), ("required_margin",), ("margin",)):
        value = _deep_number(payload, path)
        if value is not None: return value
    return None


def _extract_available_margin(payload: Any) -> float | None:
    for path in (("equity", "available", "live_balance"), ("equity", "available", "cash"), ("equity", "net"), ("available", "live_balance"), ("available", "cash"), ("net",)):
        value = _deep_number(payload, path)
        if value is not None: return value
    return None


def _deep_number(payload: Any, path: tuple[str, ...]) -> float | None:
    current = payload
    for key in path:
        if not isinstance(current, Mapping) or key not in current: return None
        current = current[key]
    if isinstance(current, (int, float)): return float(current)
    if isinstance(current, str):
        try: return float(current)
        except ValueError: return None
    return None


def _kite_client_from_env() -> tuple[Any | None, str]:
    api_key = os.environ.get("ZERODHA_API_KEY", "").strip(); access_token = os.environ.get("ZERODHA_ACCESS_TOKEN", "").strip()
    if not api_key or not access_token: return None, "ZERODHA_CREDENTIALS_UNAVAILABLE"
    try:
        from kiteconnect import KiteConnect  # type: ignore
    except Exception:
        return None, "KITECONNECT_LIBRARY_UNAVAILABLE"
    try:
        client = KiteConnect(api_key=api_key); client.set_access_token(access_token); return client, "ZERODHA_KITE_CLIENT_READY"
    except Exception:
        return None, "KITE_CLIENT_INIT_FAILED"


def _kite_instrument_key(symbol: str) -> str:
    return {"NIFTY": "NSE:NIFTY 50", "BANKNIFTY": "NSE:NIFTY BANK", "FINNIFTY": "NSE:NIFTY FIN SERVICE"}.get(symbol.upper(), f"NSE:{symbol.upper()}")


def _instrument_token_for_symbol(symbol: str) -> tuple[int | None, str]:
    normalized = {"NIFTY": "NIFTY 50", "BANKNIFTY": "NIFTY BANK", "FINNIFTY": "NIFTY FIN SERVICE"}.get(symbol.upper(), symbol.upper())
    path = Path(os.environ.get("ZERODHA_INSTRUMENT_DUMP_PATH", "data/instruments.csv").strip() or "data/instruments.csv")
    if not path.exists() or path.stat().st_size <= 0: return None, "INSTRUMENT_CSV_UNAVAILABLE"
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if row.get("exchange", "").upper() == "NSE" and row.get("tradingsymbol", "").upper() == normalized:
                    token = row.get("instrument_token", "").strip(); return (int(token), "INSTRUMENT_TOKEN_FOUND") if token else (None, "INSTRUMENT_TOKEN_EMPTY")
    except Exception:
        return None, "INSTRUMENT_CSV_READ_FAILED"
    return None, "INSTRUMENT_TOKEN_NOT_FOUND"


def _unavailable_quote(symbol: str, reason: str) -> dict[str, Any]:
    return {"symbol": symbol, "ltp": DATA_UNAVAILABLE, "open": DATA_UNAVAILABLE, "high": DATA_UNAVAILABLE, "low": DATA_UNAVAILABLE, "close": DATA_UNAVAILABLE, "change_percent": DATA_UNAVAILABLE, "volume": DATA_UNAVAILABLE, "last_update": DATA_UNAVAILABLE, "data_source": DATA_UNAVAILABLE, "validation_status": DATA_UNAVAILABLE, "connection_status": reason, "go_live_allowed": False, "message": "Live quote unavailable; no fabricated market price returned."}


def _unavailable_history(symbol: str, reason: str, interval: str = "5minute") -> dict[str, Any]:
    return {"symbol": symbol, "interval": interval, "candles": (), "data_source": DATA_UNAVAILABLE, "validation_status": DATA_UNAVAILABLE, "connection_status": reason, "go_live_allowed": False, "message": "Live history unavailable; chart must render empty state, not fabricated data."}


def _set_kill_switch(enabled: bool) -> dict[str, Any]:
    global _KILL_SWITCH_ENABLED
    _KILL_SWITCH_ENABLED = enabled
    return {"kill_switch_status": "ENABLED" if enabled else "DISABLED", "go_live_allowed": False}


def _live_block_reasons(readiness: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    if not readiness["zerodha_credentials_visible"]: reasons.append("Zerodha API key/secret unavailable")
    if not readiness["access_token_visible"]: reasons.append("Zerodha access token unavailable")
    if not readiness["expected_user_id_match"]: reasons.append("expected Zerodha user ID mismatch")
    if not readiness["instruments_csv_exists"]: reasons.append("instruments.csv unavailable")
    if not readiness["live_trading_env_enabled"]: reasons.append("LIVE_TRADING_ENABLED is not true")
    if not readiness["manual_approval_required"]: reasons.append("MANUAL_LIVE_APPROVAL_REQUIRED is not true")
    if readiness["kill_switch_status"] == "ENABLED": reasons.append("kill switch enabled")
    return reasons


def _query_symbol(query: Mapping[str, list[str]]) -> str:
    values = query.get("symbol") or ["RELIANCE"]
    return values[0].strip().upper() if values else "RELIANCE"


def _query_interval(query: Mapping[str, list[str]]) -> str:
    values = query.get("interval") or ["5minute"]
    value = values[0].strip().lower() if values else "5minute"
    return value if value in {"minute", "3minute", "5minute", "10minute", "15minute", "30minute", "60minute", "day"} else "5minute"


def _query_bool(query: Mapping[str, list[str]], key: str) -> bool:
    values = query.get(key) or ["false"]
    return values[0].strip().lower() in {"1", "true", "yes", "on"}


def _kill_switch_active() -> bool:
    return _KILL_SWITCH_ENABLED or _env_true("KILL_SWITCH_ENABLED")


def _env_true(key: str) -> bool:
    return os.environ.get(key, "false").strip().lower() in {"1", "true", "yes", "on"}


def _max_live_quantity() -> int:
    return max(_safe_int(os.environ.get("MAX_LIVE_ORDER_QTY"), 1), 1)


def _symbol_whitelist() -> set[str]:
    raw = os.environ.get("LIVE_SYMBOL_WHITELIST", "RELIANCE,INFY,TCS,NIFTY,BANKNIFTY,FINNIFTY")
    return {item.strip().upper() for item in raw.split(",") if item.strip()}


def _safe_int(value: Any, default: int) -> int:
    try: return int(value)
    except (TypeError, ValueError): return default


def _safe_float(value: Any, default: float) -> float:
    try: return float(value)
    except (TypeError, ValueError): return default


def _as_text(value: Any) -> str:
    if value is None: return DATA_UNAVAILABLE
    if isinstance(value, datetime): return value.isoformat()
    return str(value)


def _demo_bars() -> dict[str, tuple[MarketBar, ...]]:
    instrument = Instrument("DEMO", Venue.NSE, AssetClass.EQUITY, "INR")
    now = datetime.now(UTC).replace(microsecond=0)
    result: dict[str, tuple[MarketBar, ...]] = {}
    for offset, timeframe in enumerate(("1m", "3m", "5m", "15m", "30m", "1H", "4H", "Daily", "Weekly")):
        bars = []
        for index in range(24):
            close = 100 + index * (0.15 + offset * 0.01)
            bars.append(MarketBar(instrument=instrument, timestamp=now - timedelta(minutes=(24 - index) * (offset + 1)), open=close - 0.1, high=close + 0.4, low=close - 0.3, close=close, volume=10_000 + index * 125, source="DEMO_SYNTHETIC_FOR_UI_ONLY", received_at=now))
        result[timeframe] = tuple(bars)
    return result


AegisRequestHandler = AlphaGateXRequestHandler


if __name__ == "__main__":
    run()
