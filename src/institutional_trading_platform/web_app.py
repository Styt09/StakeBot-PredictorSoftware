"""Small stdlib web application for the ALPHA-GATE X Shadow Trading Platform."""

from __future__ import annotations

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
from .runtime import InMemoryAuditStore, LivePaperTradingEngine, RuntimeConfig, ShadowRunValidator

HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>ALPHA-GATE X Shadow Trading Platform</title>
  <style>
    :root {
      color-scheme: dark;
      --bg:#050a14;
      --panel:rgba(12,25,44,.82);
      --panel-strong:rgba(17,34,59,.94);
      --line:rgba(148,163,184,.22);
      --text:#edf7ff;
      --muted:#9eb5d1;
      --accent:#67e8f9;
      --accent2:#6ee7b7;
      --warn:#fbbf24;
      --danger:#fb7185;
      --shadow:0 22px 70px rgba(0,0,0,.38);
    }
    * { box-sizing:border-box; }
    body {
      margin:0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif;
      background:
        radial-gradient(circle at 20% 0%, rgba(103,232,249,.20), transparent 34%),
        radial-gradient(circle at 85% 8%, rgba(110,231,183,.16), transparent 30%),
        linear-gradient(135deg, #06101f 0%, #09162b 48%, #07111f 100%);
      color:var(--text);
      min-height:100vh;
    }
    header { padding:38px min(5vw,70px) 22px; border-bottom:1px solid var(--line); position:relative; overflow:hidden; }
    header::after { content:""; position:absolute; inset:auto -12% -42px 38%; height:145px; background:linear-gradient(90deg, transparent, rgba(103,232,249,.16), transparent); transform:rotate(-6deg); }
    h1 { margin:0; font-size:clamp(2rem, 5vw, 4.8rem); letter-spacing:.07em; line-height:1.02; }
    h2 { margin:.25rem 0 0; color:var(--accent2); font-weight:800; }
    h3 { margin:.25rem 0; }
    p { color:#d8e7f7; }
    main { padding:24px min(5vw,70px) 56px; }
    .topbar { position:sticky; top:0; z-index:5; display:flex; gap:10px; align-items:center; justify-content:space-between; margin:-24px min(-5vw,-70px) 22px; padding:10px min(5vw,70px); background:rgba(5,10,20,.74); backdrop-filter: blur(14px); border-bottom:1px solid var(--line); }
    .badge { display:inline-flex; width:max-content; align-items:center; gap:6px; border-radius:999px; padding:6px 11px; background:#0e243f; color:var(--accent2); font-size:.73rem; font-weight:900; letter-spacing:.08em; text-transform:uppercase; }
    .badge.warn { color:var(--warn); background:rgba(251,191,36,.12); }
    .badge.danger { color:var(--danger); background:rgba(251,113,133,.13); }
    .badge.info { color:var(--accent); background:rgba(103,232,249,.11); }
    .principles, .grid, .market-grid, .watchlist { display:grid; grid-template-columns:repeat(auto-fit,minmax(245px,1fr)); gap:16px; }
    .card { background:var(--panel); border:1px solid var(--line); border-radius:22px; padding:18px; box-shadow:var(--shadow); backdrop-filter:blur(16px); }
    .card.strong { background:var(--panel-strong); }
    .phase { display:flex; flex-direction:column; gap:10px; }
    .blocked { color:var(--warn); }
    .danger { color:var(--danger); }
    .shadow { margin-top:24px; }
    .kv { display:grid; grid-template-columns:repeat(auto-fit,minmax(190px,1fr)); gap:10px; }
    .kv div { background:rgba(5,17,31,.72); border:1px solid var(--line); border-radius:14px; padding:11px; min-height:58px; }
    .kv strong { color:#dbeafe; display:block; font-size:.78rem; opacity:.9; }
    .controls { display:grid; grid-template-columns:repeat(auto-fit,minmax(145px,1fr)); gap:10px; margin:12px 0; }
    button, input, select { border-radius:13px; border:1px solid var(--line); padding:11px 12px; background:rgba(5,17,31,.82); color:var(--text); min-height:42px; }
    button { cursor:pointer; font-weight:900; }
    button:hover { border-color:rgba(103,232,249,.55); }
    button[disabled] { cursor:not-allowed; opacity:.45; }
    button.danger { background:#3a1320; color:#fecdd3; border-color:#7f1d1d; }
    .action-result { margin:12px 0; background:rgba(5,17,31,.72); border:1px solid var(--line); border-radius:14px; padding:13px; }
    .action-result strong { color:var(--accent2); }
    .market-hero { display:grid; grid-template-columns: minmax(0, 1fr); gap:16px; }
    .quote-tile { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; }
    .quote-value { font-size:clamp(1.8rem,7vw,4rem); font-weight:950; line-height:1; }
    .chart-wrap { min-height:330px; display:flex; flex-direction:column; gap:10px; }
    canvas { width:100%; height:280px; background:linear-gradient(180deg, rgba(6,24,44,.92), rgba(3,10,20,.92)); border:1px solid var(--line); border-radius:18px; }
    .watch-card { cursor:pointer; transition:transform .15s ease, border-color .15s ease; }
    .watch-card:hover { transform:translateY(-2px); border-color:rgba(103,232,249,.45); }
    .muted { color:var(--muted); }
    pre { white-space:pre-wrap; overflow:auto; color:#d7e9ff; background:rgba(3,10,20,.86); padding:12px; border-radius:14px; max-height:360px; }
    a { color:var(--accent); }
    @media (min-width:900px) { .market-hero { grid-template-columns: .78fr 1.22fr; } }
  </style>
</head>
<body>
  <header>
    <span class="badge info">READ-ONLY MARKET DATA · LIVE TRADING FAIL-CLOSED</span>
    <h1>ALPHA-GATE X SHADOW TRADING PLATFORM</h1>
    <h2>Paper Trading → Shadow Trading → Manual Review</h2>
    <p>No fabricated accuracy, confidence, profitability, expected move, OI, PCR, IV, depth, flow, or alpha. Missing evidence returns <strong>DATA_UNAVAILABLE</strong>; insufficient evidence returns <strong>NO_TRADE</strong>. Live trading remains <strong>NO-GO</strong> unless strict manual gates pass.</p>
  </header>
  <main>
    <section class="topbar">
      <span class="badge info" id="connection-badge">CONNECTION · CHECKING</span>
      <span class="badge danger">AUTO LIVE TRADING DISABLED</span>
    </section>

    <section class="principles">
      <div class="card"><strong>Runtime Mode</strong><p>Paper/shadow validation first. Live auto trading is disabled.</p></div>
      <div class="card"><strong>Data Source</strong><p>Every API payload includes data_source and timestamp.</p></div>
      <div class="card"><strong>Validation Status</strong><p>Every phase reports validation_status before outputs are considered.</p></div>
    </section>

    <section class="card strong shadow">
      <span class="badge info">READ-ONLY</span>
      <h2>Live Market Dashboard</h2>
      <p class="muted">Quotes and chart data are read-only. If Zerodha live data is not connected, this dashboard shows DATA_UNAVAILABLE instead of fake prices.</p>
      <div class="controls">
        <select id="market-symbol"><option>RELIANCE</option><option>INFY</option><option>TCS</option><option>NIFTY</option><option>BANKNIFTY</option></select>
        <button onclick="refreshMarketData()">Refresh Market Data</button>
        <button onclick="loadChart()">Load Chart</button>
      </div>
      <div class="market-hero">
        <div class="card">
          <span id="quote-status" class="badge warn">DATA_UNAVAILABLE</span>
          <h3 id="quote-symbol">RELIANCE</h3>
          <div id="quote-ltp" class="quote-value">--</div>
          <div id="quote-change" class="muted">Change unavailable</div>
          <div id="quote-kv" class="kv" style="margin-top:12px"></div>
        </div>
        <div class="card chart-wrap">
          <div style="display:flex;justify-content:space-between;gap:10px;align-items:center;flex-wrap:wrap">
            <h3>Price Chart</h3>
            <span id="chart-status" class="badge warn">Live data unavailable</span>
          </div>
          <canvas id="market-chart" width="900" height="320"></canvas>
          <div id="chart-message" class="muted">Load chart to check read-only history availability.</div>
        </div>
      </div>
      <h3>Watchlist</h3>
      <div id="watchlist" class="watchlist"></div>
      <pre id="market-raw">Market payload will appear here.</pre>
    </section>

    <section class="card shadow">
      <span class="badge danger">LIVE MONEY RISK · MANUAL APPROVAL ONLY</span>
      <h2>Real Live Trading Control Panel</h2>
      <p>Automatic live trading is disabled. Live order submit remains blocked unless credentials, instruments, env gates, approval, idempotency, and risk checks pass.</p>
      <div class="controls">
        <button onclick="loadLiveReadiness()">Check Live Readiness</button>
        <button onclick="previewLiveOrder()">Preview LIMIT Order</button>
        <button id="submit-live-order" onclick="submitLiveOrder()" disabled>Submit Live Order</button>
        <button class="danger" onclick="enableKillSwitch()">Enable Kill Switch</button>
        <button onclick="resetKillSwitch()">Reset Kill Switch</button>
      </div>
      <div class="action-result">
        <strong>Last Action Result</strong>
        <div id="last-action-line">No action yet. Tap a control button.</div>
      </div>
      <div class="controls">
        <input id="live-symbol" value="RELIANCE" placeholder="Symbol" />
        <select id="live-side"><option>BUY</option><option>SELL</option></select>
        <input id="live-qty" value="1" type="number" min="1" />
        <input id="live-price" value="1" type="number" min="0" step="0.05" />
      </div>
      <div id="live-readiness" class="kv"></div>
      <pre id="live-raw">Live controls are fail-closed. Press Check Live Readiness.</pre>
    </section>

    <h2>Shadow Trading Preview Console</h2>
    <div id="phases" class="grid"></div>
    <section class="card shadow">
      <span class="badge warn">READ-ONLY · GO-LIVE DISABLED</span>
      <h2>Real Shadow Runtime Status</h2>
      <p>Live broker mutations remain disabled. Missing credentials, instruments, or WebSocket readiness are reported as unavailable instead of using fake data.</p>
      <div id="shadow-status" class="kv"></div>
      <pre id="shadow-raw">Loading shadow runtime status...</pre>
    </section>
  </main>
  <script>
    let latestPreviewId = null;
    const marketSymbols = ['RELIANCE', 'INFY', 'TCS', 'NIFTY', 'BANKNIFTY'];
    const renderKv = (target, status, keys) => {
      document.getElementById(target).innerHTML = keys.map(key => `<div><strong>${key}</strong>${status[key] ?? 'DATA_UNAVAILABLE'}</div>`).join('');
    };
    const setActionResult = (label, payload) => {
      const stamp = new Date().toLocaleTimeString();
      document.getElementById('last-action-line').textContent = `${stamp} · ${label}`;
      document.getElementById('live-raw').textContent = JSON.stringify(payload, null, 2);
    };
    const setSubmitEnabled = (enabled) => {
      document.getElementById('submit-live-order').disabled = !enabled;
    };
    const setMarketRaw = (payload) => { document.getElementById('market-raw').textContent = JSON.stringify(payload, null, 2); };
    fetch('/api/demo').then(r => r.json()).then(data => {
      document.getElementById('phases').innerHTML = data.phases.map(phase => `
        <article class="card phase">
          <span class="badge ${phase.status === 'BLOCKED' ? 'warn' : 'info'}">PHASE ${phase.phase} · ${phase.status}</span>
          <h3>${phase.name}</h3>
          <p><strong>Source:</strong> ${phase.provenance.data_source}<br><strong>Timestamp:</strong> ${phase.provenance.data_timestamp}<br><strong>Validation:</strong> ${phase.provenance.validation_status}</p>
          <pre>${JSON.stringify(phase.outputs, null, 2)}</pre>
        </article>`).join('')
    })
    function loadShadowStatus() {
      fetch('/api/shadow/status').then(r => r.json()).then(status => {
        const keys = ['mode', 'zerodha_status', 'data_source', 'total_ticks_processed', 'candles_finalized', 'signals_generated', 'paper_orders', 'fills', 'open_positions', 'closed_positions', 'realized_pnl', 'unrealized_pnl', 'total_equity', 'shadow_days_completed', 'shadow_recommendation', 'go_live_allowed'];
        renderKv('shadow-status', status, keys);
        document.getElementById('shadow-raw').textContent = JSON.stringify(status, null, 2);
      }).catch(error => {
        document.getElementById('shadow-raw').textContent = `Shadow status unavailable: ${error}`;
      })
    }
    function loadLiveReadiness() {
      setActionResult('Loading live readiness...', {status: 'LOADING'});
      fetch('/api/live/readiness').then(r => r.json()).then(status => {
        const keys = ['mode', 'zerodha_credentials_visible', 'access_token_visible', 'expected_user_id_match', 'instruments_csv_exists', 'live_trading_env_enabled', 'manual_approval_required', 'kill_switch_status', 'go_live_allowed'];
        renderKv('live-readiness', status, keys);
        document.getElementById('connection-badge').textContent = status.block_reasons && status.block_reasons.length ? 'CONNECTION · BLOCKED' : 'CONNECTION · READY';
        setSubmitEnabled(false);
        setActionResult(status.block_reasons && status.block_reasons.length ? 'Readiness BLOCKED' : 'Readiness checked', status);
      }).catch(error => setActionResult('Readiness ERROR', {error: String(error)}))
    }
    function livePayload() {
      return {symbol: document.getElementById('live-symbol').value, exchange: 'NSE', side: document.getElementById('live-side').value, quantity: Number(document.getElementById('live-qty').value), order_type: 'LIMIT', price: Number(document.getElementById('live-price').value), product: 'MIS'};
    }
    function previewLiveOrder() {
      latestPreviewId = null;
      setSubmitEnabled(false);
      setActionResult('Loading order preview...', {status: 'LOADING'});
      fetch('/api/live/order/preview', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(livePayload())}).then(r => r.json()).then(status => {
        latestPreviewId = status.preview_id || null;
        setSubmitEnabled(Boolean(status.can_submit_live_order));
        setActionResult(status.safety_gate_result === 'PASS' ? 'Preview PASS' : 'Preview BLOCKED', status);
      }).catch(error => setActionResult('Preview ERROR', {error: String(error)}));
    }
    function submitLiveOrder() {
      if (!latestPreviewId) {
        setSubmitEnabled(false);
        setActionResult('Submit BLOCKED: preview required before submit', {status:'BLOCKED', reason:'Preview required before submit'});
        return;
      }
      setActionResult('Submitting live order request...', {status: 'LOADING', preview_id: latestPreviewId});
      const payload = {...livePayload(), preview_id: latestPreviewId, typed_confirmation:'CONFIRM_LIVE_ORDER', approval_mode:true};
      fetch('/api/live/order/submit', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)}).then(r => r.json()).then(status => {
        setSubmitEnabled(false);
        setActionResult(status.status === 'BLOCKED' ? 'Submit BLOCKED' : 'Submit result', status);
      }).catch(error => setActionResult('Submit ERROR', {error: String(error)}));
    }
    function enableKillSwitch() {
      setActionResult('Enabling kill switch...', {status:'LOADING'});
      fetch('/api/live/kill-switch', {method:'POST'}).then(r => r.json()).then(status => {
        setSubmitEnabled(false);
        setActionResult('Kill switch ENABLED', status);
        loadLiveReadiness();
      }).catch(error => setActionResult('Kill switch ERROR', {error: String(error)}));
    }
    function resetKillSwitch() {
      setActionResult('Resetting kill switch...', {status:'LOADING'});
      fetch('/api/live/kill-switch/reset', {method:'POST'}).then(r => r.json()).then(status => {
        setSubmitEnabled(false);
        setActionResult('Kill switch RESET', status);
        loadLiveReadiness();
      }).catch(error => setActionResult('Kill switch reset ERROR', {error: String(error)}));
    }
    function renderWatchlist(payload) {
      const rows = payload.symbols || marketSymbols;
      document.getElementById('watchlist').innerHTML = rows.map(symbol => `<div class="card watch-card" onclick="selectMarketSymbol('${symbol}')"><span class="badge warn">DATA_UNAVAILABLE</span><h3>${symbol}</h3><p class="muted">Tap to load read-only quote.</p></div>`).join('');
    }
    function selectMarketSymbol(symbol) {
      document.getElementById('market-symbol').value = symbol;
      refreshMarketData();
      loadChart();
    }
    function refreshMarketData() {
      const symbol = document.getElementById('market-symbol').value;
      fetch(`/api/market/quote?symbol=${encodeURIComponent(symbol)}`).then(r => r.json()).then(payload => {
        document.getElementById('quote-symbol').textContent = payload.symbol || symbol;
        document.getElementById('quote-ltp').textContent = payload.ltp ?? '--';
        document.getElementById('quote-change').textContent = payload.change_percent === 'DATA_UNAVAILABLE' ? 'Change unavailable' : `${payload.change_percent}%`;
        document.getElementById('quote-status').textContent = payload.validation_status || 'DATA_UNAVAILABLE';
        renderKv('quote-kv', payload, ['open', 'high', 'low', 'close', 'volume', 'last_update', 'data_source', 'connection_status']);
        setMarketRaw(payload);
      }).catch(error => setMarketRaw({status:'ERROR', error:String(error)}));
    }
    function loadChart() {
      const symbol = document.getElementById('market-symbol').value;
      fetch(`/api/market/history?symbol=${encodeURIComponent(symbol)}`).then(r => r.json()).then(payload => {
        drawChart(payload.candles || []);
        document.getElementById('chart-status').textContent = payload.validation_status === 'VALIDATED' ? 'CHART READY' : 'Live data unavailable';
        document.getElementById('chart-message').textContent = payload.validation_status === 'VALIDATED' ? `Showing read-only history for ${symbol}` : 'Live data unavailable. No fabricated chart data is rendered.';
        setMarketRaw(payload);
      }).catch(error => setMarketRaw({status:'ERROR', error:String(error)}));
    }
    function drawChart(candles) {
      const canvas = document.getElementById('market-chart');
      const ctx = canvas.getContext('2d');
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = '#071523';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.strokeStyle = 'rgba(148,163,184,.22)';
      for (let i=0;i<6;i++) { const y = 30 + i*48; ctx.beginPath(); ctx.moveTo(28,y); ctx.lineTo(canvas.width-28,y); ctx.stroke(); }
      if (!candles.length) {
        ctx.fillStyle = '#9eb5d1';
        ctx.font = '26px system-ui';
        ctx.fillText('Live data unavailable', 46, 148);
        ctx.font = '16px system-ui';
        ctx.fillText('No fabricated chart data is rendered.', 46, 178);
        return;
      }
      const closes = candles.map(c => Number(c.close)).filter(Number.isFinite);
      const min = Math.min(...closes), max = Math.max(...closes);
      const range = Math.max(max-min, 1);
      ctx.strokeStyle = '#67e8f9'; ctx.lineWidth = 3; ctx.beginPath();
      closes.forEach((close, index) => {
        const x = 30 + index * ((canvas.width-60) / Math.max(closes.length-1, 1));
        const y = canvas.height - 35 - ((close-min)/range) * (canvas.height-70);
        if (index === 0) ctx.moveTo(x,y); else ctx.lineTo(x,y);
      });
      ctx.stroke();
    }
    fetch('/api/market/watchlist').then(r => r.json()).then(renderWatchlist).catch(() => renderWatchlist({symbols: marketSymbols}));
    refreshMarketData();
    loadChart();
    loadShadowStatus();
    loadLiveReadiness();
  </script>
</body>
</html>
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


class AlphaGateXRequestHandler(BaseHTTPRequestHandler):
    """HTTP handler exposing the ALPHA-GATE X dashboard and JSON endpoints."""

    server_version = "AlphaGateXShadowWeb/1.0"

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        """Route dashboard, health, status, demo, shadow, live, and market requests."""

        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        if path == "/":
            self._send(200, HTML, "text/html; charset=utf-8")
        elif path == "/health":
            self._send_json(200, {"status": "ok", "service": "alpha-gate-x-shadow-trading-platform"})
        elif path == "/api/status":
            self._send_json(200, {"phase_1": "complete", "active_scope": "paper_to_shadow_trading", "principle": "no fabricated trading claims", "go_live_allowed": False})
        elif path == "/api/demo":
            phases = [phase.as_dict() for phase in AegisQuantPlatform().run(_demo_bars())]
            self._send_json(200, {"mode": "UI_PREVIEW_ONLY", "go_live_allowed": False, "phases": phases})
        elif path == "/api/shadow/status":
            self._send_json(200, _shadow_status())
        elif path == "/api/live/readiness":
            self._send_json(200, _live_readiness())
        elif path == "/api/live/orders":
            self._send_json(200, _live_orders())
        elif path == "/api/safety/gates":
            self._send_json(200, _safety_gates())
        elif path == "/api/market/watchlist":
            self._send_json(200, _market_watchlist())
        elif path == "/api/market/quote":
            self._send_json(200, _market_quote(_query_symbol(query)))
        elif path == "/api/market/history":
            self._send_json(200, _market_history(_query_symbol(query)))
        else:
            self._send_json(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        """Route fail-closed live manual approval actions."""

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
        else:
            self._send_json(404, {"error": "not_found"})

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - stdlib signature
        """Silence default stderr request logging for tests and embedders."""

    def _read_json_body(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0:
            return {}
        try:
            raw = self.rfile.read(length).decode("utf-8")
            data = json.loads(raw)
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
    """Run the ALPHA-GATE X web app with Python's stdlib HTTP server."""

    ThreadingHTTPServer((host, port), AlphaGateXRequestHandler).serve_forever()


def _shadow_status() -> dict[str, Any]:
    """Return read-only paper/shadow runtime status without starting broker feeds."""

    failure_reasons: list[str] = []
    env = os.environ
    required_env = ("ZERODHA_API_KEY", "ZERODHA_ACCESS_TOKEN")
    missing_auth = tuple(key for key in required_env if not env.get(key, "").strip())
    instrument_path = env.get("ZERODHA_INSTRUMENT_DUMP_PATH", "data/instruments.csv").strip() or "data/instruments.csv"
    instruments_available = Path(instrument_path).exists() and Path(instrument_path).stat().st_size > 0
    websocket_enabled = _env_true("ENABLE_ZERODHA_WEBSOCKET")

    if missing_auth:
        failure_reasons.append(f"missing Zerodha credentials: {', '.join(missing_auth)}")
    if not instruments_available:
        failure_reasons.append(f"instrument dump unavailable: {instrument_path}")
    if not websocket_enabled:
        failure_reasons.append("read-only Zerodha WebSocket disabled")

    if missing_auth:
        zerodha_status = "ZERODHA_UNAVAILABLE"
    elif not instruments_available or not websocket_enabled:
        zerodha_status = "DATA_UNAVAILABLE"
    else:
        zerodha_status = "READ_ONLY_READY_NOT_STARTED"

    ticker_wrapper_available = ReadOnlyKiteTickerWrapper is not None
    audit_store = InMemoryAuditStore()
    engine = LivePaperTradingEngine(config=RuntimeConfig(), audit_store=audit_store)
    report = engine.build_report()
    shadow = ShadowRunValidator(audit_store).status()

    return {
        "mode": engine.config.trading_mode.value,
        "go_live_allowed": False,
        "zerodha_status": zerodha_status,
        "data_source": "RUNTIME_AUDIT_STORE" if not failure_reasons else "DATA_UNAVAILABLE",
        "total_ticks_processed": report.total_ticks_processed,
        "candles_finalized": report.candles_finalized,
        "signals_generated": report.signals_generated,
        "paper_orders": report.paper_orders,
        "fills": report.fills,
        "open_positions": report.open_positions,
        "closed_positions": report.closed_positions,
        "realized_pnl": report.realized_pnl,
        "unrealized_pnl": report.unrealized_pnl,
        "total_equity": report.total_equity,
        "max_drawdown": report.max_drawdown,
        "risk_blocks": report.risk_blocks,
        "data_quality_blocks": report.data_quality_blocks,
        "runtime_errors": report.runtime_errors,
        "shadow_days_completed": shadow.trading_days_completed,
        "shadow_recommendation": shadow.recommendation.value,
        "failure_reasons": tuple(failure_reasons + list(shadow.failure_reasons)),
        "ticker_wrapper_available": ticker_wrapper_available,
    }


def _live_readiness() -> dict[str, Any]:
    env = os.environ
    instrument_path = env.get("ZERODHA_INSTRUMENT_DUMP_PATH", "data/instruments.csv").strip() or "data/instruments.csv"
    expected_user_id = env.get("ZERODHA_EXPECTED_USER_ID", "").strip()
    actual_user_id = env.get("ZERODHA_USER_ID", expected_user_id).strip()
    readiness = {
        "mode": "LIVE_MANUAL_APPROVAL_ONLY",
        "zerodha_credentials_visible": bool(env.get("ZERODHA_API_KEY", "").strip() and env.get("ZERODHA_API_SECRET", "").strip()),
        "access_token_visible": bool(env.get("ZERODHA_ACCESS_TOKEN", "").strip()),
        "expected_user_id_match": not expected_user_id or expected_user_id == actual_user_id,
        "instruments_csv_exists": Path(instrument_path).exists() and Path(instrument_path).stat().st_size > 0,
        "live_trading_env_enabled": _env_true("LIVE_TRADING_ENABLED"),
        "manual_approval_required": _env_true("MANUAL_LIVE_APPROVAL_REQUIRED"),
        "kill_switch_status": "ENABLED" if _kill_switch_active() else "DISABLED",
        "go_live_allowed": False,
    }
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

    if exchange != "NSE":
        reasons.append("only NSE exchange is allowed in manual live mode")
    if side not in {"BUY", "SELL"}:
        reasons.append("side must be BUY or SELL")
    if order_type != "LIMIT":
        reasons.append("only LIMIT orders are allowed")
    if product not in {"MIS", "CNC"}:
        reasons.append("product must be MIS or CNC")
    if quantity < 1:
        reasons.append("quantity must be at least 1")
    if quantity > _max_live_quantity():
        reasons.append(f"quantity exceeds max allowed {_max_live_quantity()}")
    if price <= 0:
        reasons.append("limit price is required")
    if symbol not in _symbol_whitelist():
        reasons.append("symbol is not in LIVE_SYMBOL_WHITELIST")
    reasons.append("margin check unavailable")

    preview = LiveOrderPreviewState(
        preview_id=f"preview-{uuid4()}",
        idempotency_key=f"live-preview:{uuid4()}",
        symbol=symbol,
        exchange=exchange,
        side=side,
        quantity=quantity,
        order_type=order_type,
        product=product,
        price=price,
        safety_gate_result="PASS" if not reasons else "BLOCKED",
        can_submit_live_order=not reasons,
        block_reasons=tuple(dict.fromkeys(reasons)),
    )
    _PREVIEWS[preview.preview_id] = preview
    return asdict(preview)


def _live_order_submit(payload: Mapping[str, Any]) -> dict[str, Any]:
    preview_id = str(payload.get("preview_id", "")).strip()
    typed_confirmation = str(payload.get("typed_confirmation", "")).strip()
    approval_mode = bool(payload.get("approval_mode", False))
    preview = _PREVIEWS.get(preview_id)
    reasons: list[str] = []
    if preview is None:
        reasons.append("preview_id not found or expired")
    if typed_confirmation != "CONFIRM_LIVE_ORDER":
        reasons.append("typed confirmation mismatch")
    if not approval_mode:
        reasons.append("approval_mode must be true")
    if preview is not None and preview.idempotency_key in _SUBMITTED_IDEMPOTENCY_KEYS:
        reasons.append("idempotency key already used")
    if preview is not None and not preview.can_submit_live_order:
        reasons.extend(preview.block_reasons)
    if _kill_switch_active():
        reasons.append("kill switch enabled")
    readiness = _live_readiness()
    reasons.extend(readiness["block_reasons"])

    if reasons:
        return {
            "status": "BLOCKED",
            "broker_order_id": None,
            "go_live_allowed": False,
            "block_reasons": tuple(dict.fromkeys(reasons)),
        }

    return {
        "status": "BLOCKED",
        "broker_order_id": None,
        "go_live_allowed": False,
        "block_reasons": ("live broker adapter not attached to stdlib web app",),
    }


def _live_orders() -> dict[str, Any]:
    return {
        "status": "DATA_UNAVAILABLE",
        "orders": (),
        "go_live_allowed": False,
        "reason": "Zerodha order fetch adapter is not attached in this runtime",
    }


def _safety_gates() -> dict[str, Any]:
    readiness = _live_readiness()
    return {
        "go_live_allowed": False,
        "automatic_live_trading": "DISABLED",
        "manual_approval_required": readiness["manual_approval_required"],
        "kill_switch_status": readiness["kill_switch_status"],
        "order_type_allowed": "LIMIT_ONLY",
        "default_quantity": 1,
        "block_reasons": readiness["block_reasons"],
    }


def _market_watchlist() -> dict[str, Any]:
    symbols = tuple(symbol for symbol in ("RELIANCE", "INFY", "TCS", "NIFTY", "BANKNIFTY") if symbol in _symbol_whitelist() or symbol in {"NIFTY", "BANKNIFTY"})
    return {
        "symbols": symbols or ("RELIANCE", "INFY", "TCS", "NIFTY", "BANKNIFTY"),
        "data_source": "DATA_UNAVAILABLE",
        "validation_status": "DATA_UNAVAILABLE",
        "connection_status": "READ_ONLY_MARKET_DATA_NOT_CONNECTED",
        "go_live_allowed": False,
    }


def _market_quote(symbol: str) -> dict[str, Any]:
    normalized = symbol.strip().upper() or "RELIANCE"
    return {
        "symbol": normalized,
        "ltp": "DATA_UNAVAILABLE",
        "open": "DATA_UNAVAILABLE",
        "high": "DATA_UNAVAILABLE",
        "low": "DATA_UNAVAILABLE",
        "close": "DATA_UNAVAILABLE",
        "change_percent": "DATA_UNAVAILABLE",
        "volume": "DATA_UNAVAILABLE",
        "last_update": "DATA_UNAVAILABLE",
        "data_source": "DATA_UNAVAILABLE",
        "validation_status": "DATA_UNAVAILABLE",
        "connection_status": "ZERODHA_READ_ONLY_QUOTE_NOT_CONNECTED",
        "go_live_allowed": False,
        "message": "Live quote unavailable; no fabricated market price returned.",
    }


def _market_history(symbol: str) -> dict[str, Any]:
    normalized = symbol.strip().upper() or "RELIANCE"
    return {
        "symbol": normalized,
        "candles": (),
        "data_source": "DATA_UNAVAILABLE",
        "validation_status": "DATA_UNAVAILABLE",
        "connection_status": "ZERODHA_READ_ONLY_HISTORY_NOT_CONNECTED",
        "go_live_allowed": False,
        "message": "Live history unavailable; chart must render empty state, not fabricated data.",
    }


def _set_kill_switch(enabled: bool) -> dict[str, Any]:
    global _KILL_SWITCH_ENABLED
    _KILL_SWITCH_ENABLED = enabled
    return {"kill_switch_status": "ENABLED" if enabled else "DISABLED", "go_live_allowed": False}


def _live_block_reasons(readiness: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    if not readiness["zerodha_credentials_visible"]:
        reasons.append("Zerodha API key/secret unavailable")
    if not readiness["access_token_visible"]:
        reasons.append("Zerodha access token unavailable")
    if not readiness["expected_user_id_match"]:
        reasons.append("expected Zerodha user ID mismatch")
    if not readiness["instruments_csv_exists"]:
        reasons.append("instruments.csv unavailable")
    if not readiness["live_trading_env_enabled"]:
        reasons.append("LIVE_TRADING_ENABLED is not true")
    if not readiness["manual_approval_required"]:
        reasons.append("MANUAL_LIVE_APPROVAL_REQUIRED is not true")
    if readiness["kill_switch_status"] == "ENABLED":
        reasons.append("kill switch enabled")
    return reasons


def _query_symbol(query: Mapping[str, list[str]]) -> str:
    values = query.get("symbol") or ["RELIANCE"]
    return values[0].strip().upper() if values else "RELIANCE"


def _kill_switch_active() -> bool:
    return _KILL_SWITCH_ENABLED or _env_true("KILL_SWITCH_ENABLED")


def _env_true(key: str) -> bool:
    return os.environ.get(key, "false").strip().lower() in {"1", "true", "yes", "on"}


def _max_live_quantity() -> int:
    return max(_safe_int(os.environ.get("MAX_LIVE_ORDER_QTY"), 1), 1)


def _symbol_whitelist() -> set[str]:
    raw = os.environ.get("LIVE_SYMBOL_WHITELIST", "RELIANCE,INFY,TCS,NIFTY,BANKNIFTY")
    return {item.strip().upper() for item in raw.split(",") if item.strip()}


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _demo_bars() -> dict[str, tuple[MarketBar, ...]]:
    instrument = Instrument("DEMO", Venue.NSE, AssetClass.EQUITY, "INR")
    now = datetime.now(UTC).replace(microsecond=0)
    result: dict[str, tuple[MarketBar, ...]] = {}
    for offset, timeframe in enumerate(("1m", "3m", "5m", "15m", "30m", "1H", "4H", "Daily", "Weekly")):
        bars = []
        for index in range(24):
            close = 100 + index * (0.15 + offset * 0.01)
            bars.append(
                MarketBar(
                    instrument=instrument,
                    timestamp=now - timedelta(minutes=(24 - index) * (offset + 1)),
                    open=close - 0.1,
                    high=close + 0.4,
                    low=close - 0.3,
                    close=close,
                    volume=10_000 + index * 125,
                    source="DEMO_SYNTHETIC_FOR_UI_ONLY",
                    received_at=now,
                )
            )
        result[timeframe] = tuple(bars)
    return result


AegisRequestHandler = AlphaGateXRequestHandler


if __name__ == "__main__":
    run()
