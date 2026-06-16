"""Small stdlib web application for the ALPHA-GATE X Shadow Trading Platform."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse
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
    :root { color-scheme: dark; --bg:#07111f; --panel:#0f1f35; --line:#24415f; --text:#e8f2ff; --muted:#9eb5d1; --accent:#6ee7b7; --warn:#fbbf24; --danger:#fb7185; }
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
    .danger { color:var(--danger); }
    .shadow { margin-top:24px; }
    .kv { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:10px; }
    .kv div { background:#09192b; border:1px solid var(--line); border-radius:12px; padding:10px; }
    .controls { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:10px; margin:12px 0; }
    button, input, select { border-radius:10px; border:1px solid var(--line); padding:10px; background:#09192b; color:var(--text); }
    button { cursor:pointer; font-weight:800; }
    button.danger { background:#3a1320; color:#fecdd3; border-color:#7f1d1d; }
    pre { white-space:pre-wrap; overflow:auto; color:#d7e9ff; background:#071523; padding:12px; border-radius:12px; }
    a { color:var(--accent); }
  </style>
</head>
<body>
  <header>
    <h1>ALPHA-GATE X SHADOW TRADING PLATFORM</h1>
    <h2>Paper Trading → Shadow Trading → Manual Review</h2>
    <p>No fabricated accuracy, confidence, profitability, expected move, OI, PCR, IV, depth, flow, or alpha. Missing evidence returns <strong>DATA_UNAVAILABLE</strong>; insufficient evidence returns <strong>NO_TRADE</strong>. Live trading remains <strong>NO-GO</strong> unless strict manual gates pass.</p>
  </header>
  <main>
    <section class="principles">
      <div class="card"><strong>Runtime Mode</strong><p>Paper/shadow validation first. Live auto trading is disabled.</p></div>
      <div class="card"><strong>Data Source</strong><p>Every API payload includes data_source and timestamp.</p></div>
      <div class="card"><strong>Validation Status</strong><p>Every phase reports validation_status before outputs are considered.</p></div>
    </section>

    <section class="card shadow">
      <span class="status danger">LIVE MONEY RISK · MANUAL APPROVAL ONLY</span>
      <h2>Real Live Trading Control Panel</h2>
      <p>Automatic live trading is disabled. Live order submit remains blocked unless credentials, instruments, env gates, approval, idempotency, and risk checks pass.</p>
      <div class="controls">
        <button onclick="loadLiveReadiness()">Check Live Readiness</button>
        <button onclick="previewLiveOrder()">Preview LIMIT Order</button>
        <button onclick="submitLiveOrder()">Submit Live Order</button>
        <button class="danger" onclick="enableKillSwitch()">Enable Kill Switch</button>
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
      <span class="status blocked">READ-ONLY · GO-LIVE DISABLED</span>
      <h2>Real Shadow Runtime Status</h2>
      <p>Live broker mutations remain disabled. Missing credentials, instruments, or WebSocket readiness are reported as unavailable instead of using fake data.</p>
      <div id="shadow-status" class="kv"></div>
      <pre id="shadow-raw">Loading shadow runtime status...</pre>
    </section>
  </main>
  <script>
    const renderKv = (target, status, keys) => {
      document.getElementById(target).innerHTML = keys.map(key => `<div><strong>${key}</strong><br>${status[key]}</div>`).join('');
    };
    fetch('/api/demo').then(r => r.json()).then(data => {
      document.getElementById('phases').innerHTML = data.phases.map(phase => `
        <article class="card phase">
          <span class="status ${phase.status === 'BLOCKED' ? 'blocked' : ''}">PHASE ${phase.phase} · ${phase.status}</span>
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
      fetch('/api/live/readiness').then(r => r.json()).then(status => {
        const keys = ['mode', 'zerodha_credentials_visible', 'access_token_visible', 'expected_user_id_match', 'instruments_csv_exists', 'live_trading_env_enabled', 'manual_approval_required', 'kill_switch_status', 'go_live_allowed'];
        renderKv('live-readiness', status, keys);
        document.getElementById('live-raw').textContent = JSON.stringify(status, null, 2);
      })
    }
    function livePayload() {
      return {symbol: document.getElementById('live-symbol').value, exchange: 'NSE', side: document.getElementById('live-side').value, quantity: Number(document.getElementById('live-qty').value), order_type: 'LIMIT', price: Number(document.getElementById('live-price').value), product: 'MIS'};
    }
    function previewLiveOrder() {
      fetch('/api/live/order/preview', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(livePayload())}).then(r => r.json()).then(status => { document.getElementById('live-raw').textContent = JSON.stringify(status, null, 2); });
    }
    function submitLiveOrder() {
      const payload = {...livePayload(), preview_id:'manual-ui-preview', typed_confirmation:'CONFIRM_LIVE_ORDER', approval_mode:true};
      fetch('/api/live/order/submit', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)}).then(r => r.json()).then(status => { document.getElementById('live-raw').textContent = JSON.stringify(status, null, 2); });
    }
    function enableKillSwitch() {
      fetch('/api/live/kill-switch', {method:'POST'}).then(r => r.json()).then(status => { document.getElementById('live-raw').textContent = JSON.stringify(status, null, 2); loadLiveReadiness(); });
    }
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
        """Route dashboard, health, status, demo, shadow status, and live readiness requests."""

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
        elif path == "/api/safety/gates":
            self._send_json(200, _safety_gates())
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

    # No broker placement is performed by this stdlib dashboard. A separate
    # audited broker adapter must be injected only after manual certification.
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


# Backward-compatible alias for older tests/imports.
AegisRequestHandler = AlphaGateXRequestHandler


if __name__ == "__main__":
    run()
