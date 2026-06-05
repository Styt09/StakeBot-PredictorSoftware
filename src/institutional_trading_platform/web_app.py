"""Small stdlib web application for the AEGIS Quant Trading Platform."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Mapping
from urllib.parse import urlparse

from .aegis_platform import AegisQuantPlatform
from .domain import AssetClass, Instrument, MarketBar, Venue

HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>AEGIS Quant Trading Platform</title>
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
    pre { white-space:pre-wrap; overflow:auto; color:#d7e9ff; background:#071523; padding:12px; border-radius:12px; }
    a { color:var(--accent); }
  </style>
</head>
<body>
  <header>
    <h1>AEGIS QUANT TRADING PLATFORM</h1>
    <h2>Master Implementation Program · Phase 2 → Phase 24</h2>
    <p>No fabricated accuracy, confidence, profitability, expected move, OI, PCR, IV, depth, flow, or alpha. Missing evidence returns <strong>DATA_UNAVAILABLE</strong>; insufficient evidence returns <strong>NO_TRADE</strong>.</p>
  </header>
  <main>
    <section class="principles">
      <div class="card"><strong>Data Source</strong><p>Every API payload includes data_source.</p></div>
      <div class="card"><strong>Data Timestamp</strong><p>Every API payload includes data_timestamp.</p></div>
      <div class="card"><strong>Validation Status</strong><p>Every phase reports validation_status before outputs are considered.</p></div>
    </section>
    <h2>Sequential Phase Console</h2>
    <div id="phases" class="grid"></div>
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
            self._send_json(200, {"status": "ok", "service": "aegis-quant-trading-platform"})
        elif path == "/api/status":
            self._send_json(200, {"phase_1": "complete", "active_scope": "phase_2_to_phase_24", "principle": "no fabricated trading claims"})
        elif path == "/api/demo":
            phases = [phase.as_dict() for phase in AegisQuantPlatform().run(_demo_bars())]
            self._send_json(200, {"phases": phases})
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
    """Run the AEGIS web app with Python's stdlib HTTP server."""

    ThreadingHTTPServer((host, port), AegisRequestHandler).serve_forever()


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
