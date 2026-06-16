"""Small stdlib web application for the ALPHA-GATE X Shadow Trading Platform."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

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
    .shadow { margin-top:24px; }
    .kv { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:10px; }
    .kv div { background:#09192b; border:1px solid var(--line); border-radius:12px; padding:10px; }
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
      <div class="card"><strong>Runtime Mode</strong><p>Paper/shadow validation first. Live auto trading is disabled.</p></div>
      <div class="card"><strong>Data Source</strong><p>Every API payload includes data_source and timestamp.</p></div>
      <div class="card"><strong>Validation Status</strong><p>Every phase reports validation_status before outputs are considered.</p></div>
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
  </script>
</body>
</html>
"""


class AlphaGateXRequestHandler(BaseHTTPRequestHandler):
    """HTTP handler exposing the ALPHA-GATE X dashboard and JSON endpoints."""

    server_version = "AlphaGateXShadowWeb/1.0"

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        """Route dashboard, health, status, demo, and shadow status API requests."""

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
        else:
            self._send_json(404, {"error": "not_found"})

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


# Backward-compatible alias for older tests/imports.
AegisRequestHandler = AlphaGateXRequestHandler


if __name__ == "__main__":
    run()
