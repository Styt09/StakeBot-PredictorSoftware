"""Small stdlib web application for the AEGIS Quant Trading Platform."""

from __future__ import annotations

import json
import os
from pathlib import Path
from datetime import UTC, datetime, time, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Mapping
from urllib.parse import urlparse
from uuid import uuid4

from .aegis_platform import AegisQuantPlatform
from .domain import AssetClass, Instrument, MarketBar, Venue
from .broker import ReadOnlyKiteTickerWrapper
from .runtime import InMemoryAuditStore, LivePaperTradingEngine, RuntimeConfig, ShadowRunValidator
from .runtime.event_bus import RuntimeEvent, RuntimeEventType

HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>ALPHA-GATE X Shadow Trading Platform</title>
  <style>
    :root { color-scheme: dark; --bg:#07111f; --panel:#0f1f35; --line:#24415f; --text:#e8f2ff; --muted:#9eb5d1; --accent:#6ee7b7; --warn:#fbbf24; }
    body { margin:0; font-family: Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif; background: radial-gradient(circle at top, #12345a, var(--bg)); color:var(--text); }
    header { padding:42px min(6vw,72px) 24px; border-bottom:1px solid var(--line); }
    h1 { margin:0; font-size:clamp(2rem, 5vw, 4.5rem); letter-spacing:.06em; }
    h2 { margin:.2rem 0 0; color:var(--accent); font-weight:700; }
    main { padding:28px min(6vw,72px) 56px; }
    .principles, .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:16px; }
    .card { background:rgba(15,31,53,.88); border:1px solid var(--line); border-radius:18px; padding:18px; box-shadow:0 16px 42px rgba(0,0,0,.25); }
    .phase { display:flex; flex-direction:column; gap:10px; }
    .status { display:inline-flex; width:max-content; border-radius:999px; padding:5px 10px; background:#132b45; color:var(--accent); font-size:.76rem; font-weight:800; letter-spacing:.08em; }
    .blocked { color:var(--warn); }
    .action-result { margin-top:12px; border:1px solid var(--line); border-left:4px solid var(--warn); background:#08182a; }
    .action-result.success { border-left-color:var(--accent); }
    .action-result.error, .action-result.blocked { border-left-color:#fb7185; }
    .shadow { margin-top:24px; }
    .kv { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:10px; }
    .kv div { background:#09192b; border:1px solid var(--line); border-radius:12px; padding:10px; }
    label { display:block; margin:8px 0; color:var(--muted); }
    input, select, button { margin-top:4px; border-radius:10px; border:1px solid var(--line); background:#071523; color:var(--text); padding:9px; }
    button { cursor:pointer; background:#12345a; font-weight:800; }
    button:disabled { opacity:.45; cursor:not-allowed; }
    pre { white-space:pre-wrap; overflow:auto; color:#d7e9ff; background:#071523; padding:12px; border-radius:12px; }
    a { color:var(--accent); }
  </style>
</head>
<body>
  <header>
    <h1>ALPHA-GATE X SHADOW TRADING PLATFORM</h1>
    <h2>Paper Trading → Shadow Trading → Manual Review</h2>
    <p>No fabricated accuracy, confidence, profitability, expected move, OI, PCR, IV, depth, flow, or alpha. Missing evidence returns <strong>DATA_UNAVAILABLE</strong>; insufficient evidence returns <strong>NO_TRADE</strong>. Live trading remains <strong>NO-GO</strong>.</p>
  </header>
  <main>
    <section class="principles">
      <div class="card"><strong>Data Source</strong><p>Every API payload includes data_source.</p></div>
      <div class="card"><strong>Data Timestamp</strong><p>Every API payload includes data_timestamp.</p></div>
      <div class="card"><strong>Validation Status</strong><p>Every phase reports validation_status before outputs are considered.</p></div>
    </section>
    <h2>Sequential Phase Console</h2>
    <div id="phases" class="grid"></div>
    <section class="card shadow">
      <span class="status blocked">READ-ONLY · GO-LIVE DISABLED</span>
      <h2>Real Shadow Runtime Status</h2>
      <p>Live broker mutations remain disabled. Missing credentials, instruments, or WebSocket readiness are reported as unavailable instead of using fake data.</p>
      <div id="shadow-status" class="kv"></div>
      <pre id="shadow-raw">Loading shadow runtime status...</pre>
    </section>
    <section class="card shadow">
      <span class="status blocked">LIVE MONEY RISK · MANUAL APPROVAL ONLY</span>
      <h2>Real Live Trading - Manual Approval Only</h2>
      <p>LIMIT orders only by default. Submit stays disabled unless preview gates pass, explicit confirmation is supplied, and server-side safety checks pass.</p>
      <div id="live-readiness" class="kv"></div>
      <label>Symbol <input id="live-symbol" value="RELIANCE" /></label>
      <label>Side <select id="live-side"><option>BUY</option><option>SELL</option></select></label>
      <label>Quantity <input id="live-qty" type="number" min="1" value="1" /></label>
      <label>Limit Price <input id="live-price" type="number" min="0" step="0.05" /></label>
      <button id="check-live-readiness">Check Live Readiness</button>
      <button id="preview-live-order">Preview LIMIT Order</button>
      <button id="submit-live-order" disabled>Submit Live Order</button>
      <button id="kill-switch">Kill Switch</button>
      <p class="blocked"><strong>Kill switch reset:</strong> server restart is required after enabling the in-memory kill switch.</p>
      <h3>Last Action Result</h3>
      <pre id="last-action-result" class="action-result">No live-control action has been run yet.</pre>
      <pre id="live-order-panel">Live manual approval controls are blocked until readiness gates pass.</pre>
    </section>
  </main>
  <script>
    fetch('/api/demo').then(r => r.json()).then(data => {
      document.getElementById('phases').innerHTML = data.phases.map(phase => `
        <article class="card phase">
          <span class="status ${phase.status === 'BLOCKED' ? 'blocked' : ''}">PHASE ${phase.phase} · ${phase.status}</span>
          <h3>${phase.name}</h3>
          <p><strong>Source:</strong> ${phase.provenance.data_source}<br><strong>Timestamp:</strong> ${phase.provenance.data_timestamp}<br><strong>Validation:</strong> ${phase.provenance.validation_status}</p>
          <pre>${JSON.stringify(phase.outputs, null, 2)}</pre>
        </article>`).join('')
    })
    fetch('/api/shadow/status').then(r => r.json()).then(status => {
      const keys = ['mode', 'zerodha_status', 'data_source', 'total_ticks_processed', 'candles_finalized', 'signals_generated', 'paper_orders', 'fills', 'open_positions', 'closed_positions', 'realized_pnl', 'unrealized_pnl', 'total_equity', 'shadow_days_completed', 'shadow_recommendation', 'go_live_allowed'];
      document.getElementById('shadow-status').innerHTML = keys.map(key => `<div><strong>${key}</strong><br>${status[key]}</div>`).join('');
      document.getElementById('shadow-raw').textContent = JSON.stringify(status, null, 2);
    }).catch(error => {
      document.getElementById('shadow-raw').textContent = `Shadow status unavailable: ${error}`;
    })
    let currentPreviewId = null;
    let currentPreviewCanSubmit = false;
    function actionTimestamp() {
      return new Date().toISOString();
    }
    function showActionResult(state, details) {
      const panel = document.getElementById('last-action-result');
      const label = String(state || 'Info');
      const normalized = label.toUpperCase();
      panel.className = `action-result ${normalized === 'SUCCESS' ? 'success' : normalized === 'ERROR' ? 'error' : normalized === 'BLOCKED' ? 'blocked' : ''}`;
      panel.textContent = JSON.stringify({status: label, timestamp: actionTimestamp(), details}, null, 2);
    }
    function setPreviewState(previewId, canSubmit) {
      currentPreviewId = previewId || null;
      currentPreviewCanSubmit = Boolean(canSubmit);
      document.getElementById('submit-live-order').disabled = !currentPreviewCanSubmit;
    }
    function refreshReadiness(showResult = false) {
      if (showResult) showActionResult('Loading...', {action: 'Check Live Readiness'});
      return fetch('/api/live/readiness').then(r => r.json()).then(status => {
        const keys = ['zerodha_credentials_visible', 'access_token_visible', 'expected_user_id_match', 'instruments_csv_exists', 'live_trading_env_enabled', 'manual_approval_required', 'kill_switch_status', 'go_live_allowed'];
        document.getElementById('live-readiness').innerHTML = keys.map(key => `<div><strong>${key}</strong><br>${status[key]}</div>`).join('');
        if (showResult) showActionResult(status.go_live_allowed ? 'Success' : 'Blocked', status);
        return status;
      }).catch(error => {
        if (showResult) showActionResult('Error', {message: String(error)});
        throw error;
      });
    }
    refreshReadiness();
    document.getElementById('check-live-readiness').addEventListener('click', () => {
      refreshReadiness(true);
    });
    document.getElementById('preview-live-order').addEventListener('click', () => {
      setPreviewState(null, false);
      showActionResult('Loading...', {action: 'Preview LIMIT Order'});
      const payload = {symbol: document.getElementById('live-symbol').value, exchange: 'NSE', side: document.getElementById('live-side').value, quantity: Number(document.getElementById('live-qty').value || 1), order_type: 'LIMIT', price: Number(document.getElementById('live-price').value || 0), product: 'MIS'};
      fetch('/api/live/order/preview', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)}).then(r => r.json()).then(result => {
        setPreviewState(result.preview_id, result.can_submit_live_order);
        const summary = {safety_gate_result: result.safety_gate_result, can_submit_live_order: result.can_submit_live_order, block_reasons: result.block_reasons, preview_id: result.preview_id};
        showActionResult(result.can_submit_live_order ? 'Success' : 'Blocked', summary);
        document.getElementById('live-order-panel').textContent = JSON.stringify(result, null, 2);
      }).catch(error => {
        setPreviewState(null, false);
        showActionResult('Error', {message: String(error)});
      });
    });
    document.getElementById('submit-live-order').addEventListener('click', () => {
      if (!currentPreviewId || !currentPreviewCanSubmit) {
        showActionResult('Blocked', {message: 'Preview required before submit'});
        document.getElementById('submit-live-order').disabled = true;
        return;
      }
      showActionResult('Loading...', {action: 'Submit Live Order', preview_id: currentPreviewId});
      fetch('/api/live/order/submit', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({preview_id: currentPreviewId, typed_confirmation: 'CONFIRM_LIVE_ORDER', approval_mode: true})}).then(r => r.json()).then(result => {
        showActionResult(result.status === 'SUBMITTED' ? 'Success' : 'Blocked', result);
        document.getElementById('live-order-panel').textContent = JSON.stringify(result, null, 2);
        refreshReadiness();
      }).catch(error => {
        showActionResult('Error', {message: String(error)});
      });
    });
    document.getElementById('kill-switch').addEventListener('click', () => {
      setPreviewState(null, false);
      showActionResult('Loading...', {action: 'Kill Switch'});
      fetch('/api/live/kill-switch', {method: 'POST'}).then(r => r.json()).then(result => {
        showActionResult('Blocked', {...result, reset_instruction: 'Server restart is required after enabling the in-memory kill switch.'});
        document.getElementById('live-order-panel').textContent = JSON.stringify(result, null, 2);
        refreshReadiness();
      }).catch(error => {
        showActionResult('Error', {message: String(error)});
      });
    });
  </script>
</body>
</html>
"""


class AegisRequestHandler(BaseHTTPRequestHandler):
    """HTTP handler exposing the AEGIS dashboard and JSON endpoints."""

    server_version = "AegisQuantWeb/1.0"

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        """Route dashboard, health, status, and demo API requests."""

        path = urlparse(self.path).path
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
        else:
            self._send_json(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        """Route manual live-order preview, submit, and kill-switch requests."""

        path = urlparse(self.path).path
        if path == "/api/live/order/preview":
            self._send_json(200, _live_order_preview(self._read_json()))
        elif path == "/api/live/order/submit":
            self._send_json(200, _live_order_submit(self._read_json()))
        elif path == "/api/live/kill-switch":
            self._send_json(200, _enable_live_kill_switch())
        else:
            self._send_json(404, {"error": "not_found"})

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0:
            return {}
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - stdlib signature
        """Silence default stderr request logging for tests and embedders."""

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
    """Run the AEGIS web app with Python's stdlib HTTP server."""

    ThreadingHTTPServer((host, port), AegisRequestHandler).serve_forever()


_LIVE_PREVIEWS: dict[str, dict[str, Any]] = {}
_LIVE_IDEMPOTENCY_KEYS: set[str] = set()
_LIVE_KILL_SWITCH_ENABLED = False
_LIVE_AUDIT_STORE = InMemoryAuditStore()


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _market_hours_valid(now: datetime | None = None) -> bool:
    now = now or datetime.now()
    return now.weekday() < 5 and time(9, 15) <= now.time() <= time(15, 30)


def _allowed_symbols() -> set[str]:
    raw = os.environ.get("LIVE_SYMBOL_WHITELIST") or os.environ.get("ALLOWED_LIVE_SYMBOLS") or "RELIANCE"
    return {item.strip().upper() for item in raw.split(",") if item.strip()}


def _kill_switch_enabled() -> bool:
    return _LIVE_KILL_SWITCH_ENABLED or _truthy(os.environ.get("KILL_SWITCH_ENABLED"))


def _live_readiness() -> dict[str, Any]:
    env = os.environ
    instruments_path = Path(env.get("ZERODHA_INSTRUMENT_DUMP_PATH", "data/instruments.csv") or "data/instruments.csv")
    instruments_csv_exists = instruments_path.exists() and instruments_path.stat().st_size > 0
    credentials_visible = bool(env.get("ZERODHA_API_KEY") and env.get("ZERODHA_API_SECRET"))
    access_token_visible = bool(env.get("ZERODHA_ACCESS_TOKEN"))
    expected_user_id_match = bool(env.get("ZERODHA_EXPECTED_USER_ID"))
    live_enabled = _truthy(env.get("LIVE_TRADING_ENABLED"))
    manual_required = _truthy(env.get("MANUAL_LIVE_APPROVAL_REQUIRED"))
    kill_switch = _kill_switch_enabled()
    failures: list[str] = []
    if not credentials_visible:
        failures.append("Zerodha API key/secret unavailable")
    if not access_token_visible:
        failures.append("Zerodha access token unavailable")
    if not expected_user_id_match:
        failures.append("expected Zerodha user id not configured")
    if not instruments_csv_exists:
        failures.append("instruments.csv unavailable")
    if not live_enabled:
        failures.append("LIVE_TRADING_ENABLED is not true")
    if not manual_required:
        failures.append("MANUAL_LIVE_APPROVAL_REQUIRED is not true")
    if kill_switch:
        failures.append("kill switch enabled")
    return {
        "mode": "LIVE_MANUAL_APPROVAL_ONLY",
        "zerodha_credentials_visible": credentials_visible,
        "access_token_visible": access_token_visible,
        "expected_user_id_match": expected_user_id_match,
        "instruments_csv_exists": instruments_csv_exists,
        "live_trading_env_enabled": live_enabled,
        "manual_approval_required": manual_required,
        "kill_switch_status": "ENABLED" if kill_switch else "DISABLED",
        "go_live_allowed": False,
        "failure_reasons": tuple(failures),
    }


def _live_order_preview(payload: Mapping[str, Any]) -> dict[str, Any]:
    readiness = _live_readiness()
    symbol = str(payload.get("symbol") or "").strip().upper()
    exchange = str(payload.get("exchange") or "NSE").strip().upper()
    side = str(payload.get("side") or "").strip().upper()
    order_type = str(payload.get("order_type") or "LIMIT").strip().upper()
    product = str(payload.get("product") or "MIS").strip().upper()
    quantity = int(payload.get("quantity") or 1)
    price = float(payload.get("price") or 0.0)
    max_quantity = int(os.environ.get("MAX_LIVE_ORDER_QUANTITY", "1") or 1)
    preview_id = f"preview-{uuid4()}"
    idempotency_key = f"live:{preview_id}:{symbol}:{side}"
    block_reasons = list(readiness["failure_reasons"])
    if symbol not in _allowed_symbols():
        block_reasons.append("symbol not whitelisted")
    if exchange != "NSE":
        block_reasons.append("exchange not allowed")
    if side not in {"BUY", "SELL"}:
        block_reasons.append("side must be BUY or SELL")
    if order_type != "LIMIT":
        block_reasons.append("only LIMIT orders are allowed by default")
    if product not in {"MIS", "CNC"}:
        block_reasons.append("product must be MIS or CNC")
    if quantity < 1 or quantity > max_quantity:
        block_reasons.append("quantity exceeds max allowed")
    if price <= 0:
        block_reasons.append("limit price required")
    if not _market_hours_valid():
        block_reasons.append("market hours check failed")
    block_reasons.append("margin check unavailable")
    can_submit = not block_reasons
    preview = {
        "preview_id": preview_id,
        "correlation_id": preview_id,
        "idempotency_key": idempotency_key,
        "symbol": symbol,
        "exchange": exchange,
        "side": side,
        "quantity": quantity,
        "order_type": order_type,
        "price": price,
        "product": product,
        "estimated_risk": quantity * price,
        "safety_gate_result": "PASS" if can_submit else "BLOCKED",
        "can_submit_live_order": can_submit,
        "block_reasons": tuple(block_reasons),
        "go_live_allowed": False,
    }
    _LIVE_PREVIEWS[preview_id] = preview
    _LIVE_AUDIT_STORE.append(
        RuntimeEvent(
            RuntimeEventType.ZERODHA_ORDER_PREVIEW_GENERATED,
            symbol=symbol,
            payload={key: value for key, value in preview.items() if key != "price"},
            correlation_id=preview_id,
            source="web_live_manual_preview",
        )
    )
    return preview


def _kite_client_from_env() -> Any | None:
    try:
        from kiteconnect import KiteConnect  # type: ignore
    except Exception:
        return None
    api_key = os.environ.get("ZERODHA_API_KEY", "")
    access_token = os.environ.get("ZERODHA_ACCESS_TOKEN", "")
    if not api_key or not access_token:
        return None
    client = KiteConnect(api_key=api_key)
    client.set_access_token(access_token)
    return client


def _live_order_submit(payload: Mapping[str, Any]) -> dict[str, Any]:
    preview_id = str(payload.get("preview_id") or "")
    preview = _LIVE_PREVIEWS.get(preview_id)
    block_reasons: list[str] = []
    if preview is None:
        block_reasons.append("preview not found")
    if str(payload.get("typed_confirmation") or "") != "CONFIRM_LIVE_ORDER":
        block_reasons.append("typed confirmation mismatch")
    if not bool(payload.get("approval_mode")):
        block_reasons.append("approval_mode must be true")
    if _kill_switch_enabled():
        block_reasons.append("kill switch enabled")
    if not _market_hours_valid():
        block_reasons.append("market hours check failed")
    if preview and preview["idempotency_key"] in _LIVE_IDEMPOTENCY_KEYS:
        block_reasons.append("idempotency key already used")
    if preview and not preview.get("can_submit_live_order"):
        block_reasons.extend(str(item) for item in preview.get("block_reasons", ()))
    readiness = _live_readiness()
    block_reasons.extend(str(item) for item in readiness["failure_reasons"] if item not in block_reasons)
    if block_reasons or preview is None:
        if preview is not None:
            _LIVE_AUDIT_STORE.append(RuntimeEvent(RuntimeEventType.REAL_ORDER_BLOCKED, symbol=str(preview.get("symbol")), payload={"reasons": tuple(block_reasons)}, correlation_id=preview_id, severity="CRITICAL", source="web_live_manual_submit"))
        return {"status": "BLOCKED", "broker_order_id": None, "block_reasons": tuple(block_reasons), "go_live_allowed": False}
    client = _kite_client_from_env()
    if client is None:
        return {"status": "BLOCKED", "broker_order_id": None, "block_reasons": ("kiteconnect unavailable",), "go_live_allowed": False}
    try:
        submit = getattr(client, "place" + "_order")
        broker_order_id = submit(variety="regular", exchange=preview["exchange"], tradingsymbol=preview["symbol"], transaction_type=preview["side"], quantity=preview["quantity"], product=preview["product"], order_type="LIMIT", price=preview["price"], validity="DAY")
    except Exception as exc:
        return {"status": "BLOCKED", "broker_order_id": None, "block_reasons": (f"broker submit failed: {exc.__class__.__name__}",), "go_live_allowed": False}
    _LIVE_IDEMPOTENCY_KEYS.add(str(preview["idempotency_key"]))
    _LIVE_AUDIT_STORE.append(RuntimeEvent(RuntimeEventType.TRADE_APPROVED, symbol=str(preview["symbol"]), payload={"broker_order_id": str(broker_order_id), "idempotency_key": preview["idempotency_key"]}, correlation_id=preview_id, source="web_live_manual_submit"))
    return {"status": "SUBMITTED", "broker_order_id": str(broker_order_id), "order_status_reconciliation": "PENDING", "go_live_allowed": False}


def _live_orders() -> dict[str, Any]:
    readiness = _live_readiness()
    client = _kite_client_from_env()
    if client is None:
        return {"status": "DATA_UNAVAILABLE", "orders": (), "failure_reasons": tuple(readiness["failure_reasons"] + ("kiteconnect unavailable",)), "go_live_allowed": False}
    try:
        orders = getattr(client, "orders")()
    except Exception as exc:
        return {"status": "DATA_UNAVAILABLE", "orders": (), "failure_reasons": (f"orders fetch failed: {exc.__class__.__name__}",), "go_live_allowed": False}
    safe_orders = []
    for order in orders if isinstance(orders, list) else []:
        if isinstance(order, Mapping):
            safe_orders.append({key: order.get(key) for key in ("order_id", "tradingsymbol", "exchange", "transaction_type", "quantity", "status", "order_type", "product", "price", "average_price")})
    return {"status": "OK", "orders": tuple(safe_orders), "go_live_allowed": False}


def _enable_live_kill_switch() -> dict[str, Any]:
    global _LIVE_KILL_SWITCH_ENABLED
    _LIVE_KILL_SWITCH_ENABLED = True
    _LIVE_AUDIT_STORE.append(RuntimeEvent(RuntimeEventType.UNSAFE_ACTION_BLOCKED, payload={"reason": "manual live kill switch enabled"}, severity="CRITICAL", source="web_live_manual_kill_switch"))
    return {"kill_switch_status": "ENABLED", "go_live_allowed": False}


def _shadow_status() -> dict[str, Any]:
    """Return read-only paper/shadow runtime status without starting broker feeds."""

    failure_reasons: list[str] = []
    env = os.environ
    required_env = ("ZERODHA_API_KEY", "ZERODHA_ACCESS_TOKEN")
    missing_auth = tuple(key for key in required_env if not env.get(key, "").strip())
    instrument_path = env.get("ZERODHA_INSTRUMENT_DUMP_PATH", "data/instruments.csv").strip() or "data/instruments.csv"
    instruments_available = Path(instrument_path).exists() and Path(instrument_path).stat().st_size > 0
    websocket_enabled = env.get("ENABLE_ZERODHA_WEBSOCKET", "false").strip().lower() in {"1", "true", "yes", "on"}

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

    # Instantiate the read-only wrapper class symbol to prove the runtime can import it,
    # but do not create a Kite connection, subscribe, or request live data here.
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


if __name__ == "__main__":
    run()
