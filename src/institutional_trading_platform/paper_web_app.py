"""Deployable paper-trading PWA for ALPHA-GATE X.

The service exposes virtual paper trading only. It never submits broker orders.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import parse_qs, urlparse

from .paper_engine import PaperEngine

APP_NAME = "ALPHA-GATE X Paper"
DB_PATH = os.environ.get("PAPER_DB_PATH", "data/paper_trading.db")
STARTING_BALANCE = float(os.environ.get("PAPER_STARTING_BALANCE", "100000"))
ACCESS_TOKEN = os.environ.get("APP_ACCESS_TOKEN", "").strip()
ENGINE = PaperEngine(DB_PATH, starting_balance=STARTING_BALANCE)


def _session_value() -> str:
    if not ACCESS_TOKEN:
        return ""
    return hashlib.sha256((ACCESS_TOKEN + "|alpha-gate-paper").encode()).hexdigest()


def _json_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, indent=2, default=str).encode("utf-8")


def _clean_symbol(value: str) -> str:
    return (value or "RELIANCE").strip().upper()


def _quote(symbol: str) -> dict[str, Any]:
    normalized = _clean_symbol(symbol)
    api_key = os.environ.get("ZERODHA_API_KEY", "").strip()
    access_token = os.environ.get("ZERODHA_ACCESS_TOKEN", "").strip()
    if not api_key or not access_token:
        return {
            "symbol": normalized,
            "ltp": "DATA_UNAVAILABLE",
            "status": "BLOCKED",
            "reason": "ZERODHA_CREDENTIALS_UNAVAILABLE",
            "real_order": False,
            "go_live_allowed": False,
        }
    try:
        from kiteconnect import KiteConnect  # type: ignore

        client = KiteConnect(api_key=api_key)
        client.set_access_token(access_token)
        key = {
            "NIFTY": "NSE:NIFTY 50",
            "BANKNIFTY": "NSE:NIFTY BANK",
            "FINNIFTY": "NSE:NIFTY FIN SERVICE",
        }.get(normalized, f"NSE:{normalized}")
        row = client.quote([key]).get(key) or {}
        ltp = row.get("last_price")
        if not isinstance(ltp, (int, float)) or ltp <= 0:
            raise ValueError("quote unavailable")
        ENGINE.mark_price(normalized, float(ltp))
        return {
            "symbol": normalized,
            "ltp": float(ltp),
            "status": "PASS",
            "data_source": "ZERODHA_KITE_QUOTE",
            "real_order": False,
            "go_live_allowed": False,
        }
    except Exception as exc:
        return {
            "symbol": normalized,
            "ltp": "DATA_UNAVAILABLE",
            "status": "BLOCKED",
            "reason": f"ZERODHA_QUOTE_UNAVAILABLE:{exc.__class__.__name__}",
            "real_order": False,
            "go_live_allowed": False,
        }


MANIFEST = {
    "name": APP_NAME,
    "short_name": "AlphaGate",
    "start_url": "/",
    "display": "standalone",
    "background_color": "#06101f",
    "theme_color": "#06101f",
    "description": "Persistent virtual paper trading. Real orders disabled.",
    "icons": [],
}

SW_JS = """
const CACHE='alpha-gate-paper-v1';
self.addEventListener('install',event=>event.waitUntil(caches.open(CACHE).then(c=>c.addAll(['/','/manifest.webmanifest']))));
self.addEventListener('activate',event=>event.waitUntil(self.clients.claim()));
self.addEventListener('fetch',event=>{
  if(event.request.method!=='GET') return;
  event.respondWith(fetch(event.request).catch(()=>caches.match(event.request)));
});
"""

LOGIN_HTML = """<!doctype html><html><head><meta name='viewport' content='width=device-width,initial-scale=1'><title>ALPHA-GATE X Login</title><style>body{margin:0;background:#06101f;color:#eef7ff;font-family:system-ui;display:grid;place-items:center;min-height:100vh}.box{width:min(92vw,420px);background:#0b1728;border:1px solid #29415f;border-radius:24px;padding:22px}input,button{width:100%;box-sizing:border-box;padding:14px;border-radius:14px;border:1px solid #35506f;background:#071523;color:#fff;margin-top:10px}button{background:#2563eb;font-weight:900}.bad{color:#fecaca}</style></head><body><form class='box' method='post' action='/login'><h1>ALPHA-GATE X</h1><p>Paper trading access</p><input type='password' name='token' placeholder='App access token' required><button>LOGIN</button><p class='bad'>Real broker orders are disabled.</p></form></body></html>"""

APP_HTML = r"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#06101f"><link rel="manifest" href="/manifest.webmanifest">
<title>ALPHA-GATE X Paper</title>
<style>
:root{color-scheme:dark;--bg:#06101f;--panel:#0b1728;--line:#29415f;--text:#eef7ff;--muted:#9eb3cc;--buy:#16a34a;--sell:#e11d48;--blue:#2563eb}*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 10% 0%,#0b3350,transparent 34%),var(--bg);color:var(--text);font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif}.wrap{max-width:980px;margin:auto;padding:16px 14px 60px}.top{position:sticky;top:0;z-index:20;display:flex;gap:7px;flex-wrap:wrap;padding:10px 0;background:rgba(6,16,31,.9);backdrop-filter:blur(14px)}.badge{padding:7px 10px;border-radius:999px;background:#12314a;color:#b9f5ff;font-size:.72rem;font-weight:900}.red{background:#401522;color:#fecaca}.green{background:#123c2c;color:#bbf7d0}.card{background:linear-gradient(180deg,#0e2035,#091625);border:1px solid var(--line);border-radius:22px;padding:16px;margin:14px 0;box-shadow:0 20px 60px #0006}h1{font-size:clamp(2rem,8vw,4rem);line-height:.95;margin:12px 0}h2{color:#bbf7d0}.grid{display:grid;grid-template-columns:1fr;gap:10px}.two{display:grid;grid-template-columns:1fr 1fr;gap:10px}label{font-size:.75rem;font-weight:900;color:#dbeafe;text-transform:uppercase}input,select,button{width:100%;min-height:46px;border:1px solid var(--line);border-radius:14px;background:#071523;color:#fff;padding:11px 12px;font-weight:850}button{cursor:pointer}.buy{background:var(--buy)}.sell{background:var(--sell)}.blue{background:var(--blue)}.active{outline:3px solid #fbbf24}.price{font-size:2.5rem;font-weight:1000;color:#fb7185}.kv{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}.kv div{background:#071523;border:1px solid var(--line);border-radius:14px;padding:10px;overflow-wrap:anywhere}.kv small{display:block;color:var(--muted);text-transform:uppercase}.row{padding:12px 0;border-bottom:1px solid var(--line)}pre{white-space:pre-wrap;max-height:260px;overflow:auto;background:#020617;border-radius:14px;padding:12px}.muted{color:var(--muted)}@media(min-width:760px){.grid{grid-template-columns:repeat(2,1fr)}.kv{grid-template-columns:repeat(3,1fr)}}
</style></head><body><div class="wrap">
<div class="top"><span class="badge green">PAPER MODE</span><span class="badge red">REAL ORDERS DISABLED</span><span class="badge" id="connection">READY</span><button style="width:auto;min-height:34px;padding:6px 10px" onclick="location.href='/logout'">Logout</button></div>
<section><h1>ALPHA-GATE X<br>Paper Trading</h1><p class="muted">One clean ticket, persistent SQLite portfolio, exact backend reasons, PWA install support.</p></section>
<div class="grid">
<section class="card"><h2>Paper Buy / Sell Ticket</h2>
<label>Symbol</label><input id="symbol" value="RELIANCE" list="symbols"><datalist id="symbols"><option value="RELIANCE"><option value="TCS"><option value="INFY"><option value="HDFCBANK"><option value="ICICIBANK"><option value="SBIN"><option value="NIFTY"><option value="BANKNIFTY"><option value="FINNIFTY"><option value="GOLDBEES"></datalist>
<div class="two"><button id="buy" class="buy active">BUY</button><button id="sell" class="sell">SELL</button></div>
<div class="two"><div><label>Product</label><select id="product"><option value="MIS">MIS / Intraday</option><option value="CNC">CNC / Delivery</option></select></div><div><label>Order type</label><select id="orderType"><option value="LIMIT">LIMIT</option><option value="MARKET">MARKET</option></select></div></div>
<div class="two"><div><label>Lots</label><input id="lots" type="number" min="1" value="1"></div><div><label>Lot size</label><input id="lotSize" type="number" min="1" value="1"></div></div>
<label>Limit price</label><input id="price" type="number" step="0.05" min="0" value="0">
<div class="two"><div><label>Stop loss</label><input id="stop" type="number" step="0.05" value="0"></div><div><label>Target 1</label><input id="target1" type="number" step="0.05" value="0"></div></div>
<label>Target 2</label><input id="target2" type="number" step="0.05" value="0">
<p id="preview" class="muted">Qty 1 · Margin ₹0</p><button id="place" class="buy">PLACE PAPER BUY</button><pre id="result">Ready.</pre>
</section>
<section class="card"><h2>Live Quote</h2><div class="price" id="ltp">--</div><p id="quoteReason" class="muted">Quote not loaded.</p><button class="blue" id="quoteBtn">Refresh Quote</button><h2>Account</h2><div id="summary" class="kv"></div><div class="two"><input id="balance" type="number" value="10000" min="1"><button id="addBalance" class="blue">Add Virtual Balance</button></div><button id="reset" class="sell">Reset Paper Account</button></section>
</div>
<section class="card"><h2>Open Positions</h2><div id="positions">No open positions.</div></section>
<section class="card"><h2>Closed Trades</h2><div id="trades">No closed trades.</div></section>
</div><script>
let side='BUY';const $=id=>document.getElementById(id);const num=(v,d=0)=>{const x=Number(v);return Number.isFinite(x)?x:d};const money=v=>'₹'+Number(v||0).toLocaleString('en-IN',{maximumFractionDigits:2});
async function api(url,opt){const r=await fetch(url,Object.assign({cache:'no-store'},opt||{}));const t=await r.text();try{return JSON.parse(t)}catch{return {status:'BLOCKED',reason:'NON_JSON_RESPONSE',raw:t}}}
async function post(url,p){return api(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(p||{})})}
function setSide(s){side=s;$('buy').classList.toggle('active',s==='BUY');$('sell').classList.toggle('active',s==='SELL');$('place').className=s==='BUY'?'buy':'sell';$('place').textContent='PLACE PAPER '+s;preview()}
function qty(){return Math.max(1,num($('lots').value,1))*Math.max(1,num($('lotSize').value,1))}
function preview(){const q=qty(),p=num($('price').value),factor=$('product').value==='MIS'?.2:1;$('preview').textContent=`Qty ${q} · Estimated margin ${money(q*p*factor)}`;$('price').disabled=$('orderType').value==='MARKET'}
async function quote(){const sym=$('symbol').value.trim().toUpperCase()||'RELIANCE';const out=await api('/api/quote?symbol='+encodeURIComponent(sym));$('ltp').textContent=typeof out.ltp==='number'?money(out.ltp):'--';$('quoteReason').textContent=out.status==='PASS'?out.data_source:(out.reason||'Quote unavailable');$('connection').textContent=out.status==='PASS'?'ZERODHA CONNECTED':'LIMIT MODE READY';if(out.status==='PASS'&&!num($('price').value))$('price').value=Number(out.ltp).toFixed(2);preview();return out}
async function place(){const req={symbol:$('symbol').value.trim().toUpperCase(),side,product:$('product').value,order_type:$('orderType').value,lots:Math.max(1,num($('lots').value,1)),lot_size:Math.max(1,num($('lotSize').value,1)),quantity:qty(),limit_price:num($('price').value),entry_price:num($('price').value),stop_loss:num($('stop').value),target_1:num($('target1').value),target_2:num($('target2').value),real_order:false,go_live_allowed:false};const out=await post('/api/paper/order',req);$('result').textContent=JSON.stringify({request:req,response:out},null,2);if(out.status!=='PASS')alert('Blocked: '+(out.reason||'UNKNOWN'));await status()}
async function closePosition(id,price){const out=await post('/api/paper/close',{position_id:id,exit_price:num(price)});$('result').textContent=JSON.stringify(out,null,2);if(out.status!=='PASS')alert('Blocked: '+(out.reason||'UNKNOWN'));status()}
async function status(){const out=await api('/api/paper/status');const s=out.account_summary||{};$('summary').innerHTML=['cash_balance','reserved_margin','equity','realized_pnl','unrealized_pnl','open_position_count'].map(k=>`<div><small>${k}</small>${s[k]??'--'}</div>`).join('');$('positions').innerHTML=(out.open_positions||[]).map(p=>`<div class="row"><b>${p.symbol} ${p.side} × ${p.quantity}</b><br>Lots ${p.lots} · Lot size ${p.lot_size} · ${p.product}<br>Entry ${p.entry_price} · LTP ${p.last_price} · P&L ${p.unrealized_pnl}<br><button class="sell" onclick="closePosition('${p.position_id}',${p.last_price})">EXIT</button></div>`).join('')||'No open positions.';$('trades').innerHTML=(out.closed_trades||[]).slice(0,20).map(t=>`<div class="row"><b>${t.symbol} ${t.side} × ${t.quantity}</b><br>${t.entry_price} → ${t.exit_price} · P&L ${t.pnl} · ${t.exit_reason}</div>`).join('')||'No closed trades.'}
$('buy').onclick=()=>setSide('BUY');$('sell').onclick=()=>setSide('SELL');$('place').onclick=place;$('quoteBtn').onclick=quote;$('addBalance').onclick=async()=>{const out=await post('/api/paper/balance/add',{amount:num($('balance').value)});$('result').textContent=JSON.stringify(out,null,2);status()};$('reset').onclick=async()=>{if(confirm('Reset all paper positions and trades?')){const out=await post('/api/paper/reset',{starting_balance:100000});$('result').textContent=JSON.stringify(out,null,2);status()}};['lots','lotSize','price','product','orderType'].forEach(id=>$(id).oninput=preview);$('symbol').onchange=()=>{$('price').value=0;quote()};preview();status();quote();setInterval(()=>{if(!document.hidden){status();quote()}},5000);if('serviceWorker'in navigator)navigator.serviceWorker.register('/sw.js');
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    server_version = "AlphaGatePaper/1.0"

    def _authenticated(self) -> bool:
        if not ACCESS_TOKEN:
            return True
        header = self.headers.get("Authorization", "")
        if header.startswith("Bearer ") and hmac.compare_digest(header[7:], ACCESS_TOKEN):
            return True
        jar = cookies.SimpleCookie(self.headers.get("Cookie", ""))
        item = jar.get("alpha_gate_session")
        return bool(item and hmac.compare_digest(item.value, _session_value()))

    def _require_auth(self) -> bool:
        if self._authenticated():
            return True
        if self.path.startswith("/api/"):
            self._send_json(401, {"status": "BLOCKED", "reason": "AUTH_REQUIRED", "real_order": False, "go_live_allowed": False})
        else:
            self._send(200, LOGIN_HTML.encode(), "text/html; charset=utf-8")
        return False

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/health":
            self._send_json(200, {"status": "ok", "service": "alpha-gate-paper", "real_order": False, "go_live_allowed": False})
            return
        if path == "/manifest.webmanifest":
            self._send(200, _json_bytes(MANIFEST), "application/manifest+json")
            return
        if path == "/sw.js":
            self._send(200, SW_JS.encode(), "application/javascript; charset=utf-8")
            return
        if path == "/logout":
            self.send_response(302)
            self.send_header("Set-Cookie", "alpha_gate_session=; Max-Age=0; Path=/; HttpOnly; SameSite=Strict")
            self.send_header("Location", "/")
            self.end_headers()
            return
        if not self._require_auth():
            return
        if path == "/":
            self._send(200, APP_HTML.encode(), "text/html; charset=utf-8")
        elif path == "/api/paper/status":
            self._send_json(200, ENGINE.status())
        elif path == "/api/quote":
            symbol = (parse_qs(parsed.query).get("symbol") or ["RELIANCE"])[0]
            self._send_json(200, _quote(symbol))
        else:
            self._send_json(404, {"status": "BLOCKED", "reason": "NOT_FOUND", "real_order": False, "go_live_allowed": False})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/login":
            length = int(self.headers.get("Content-Length", "0") or 0)
            form = parse_qs(self.rfile.read(length).decode("utf-8", errors="ignore"))
            supplied = (form.get("token") or [""])[0]
            if ACCESS_TOKEN and hmac.compare_digest(supplied, ACCESS_TOKEN):
                self.send_response(302)
                self.send_header("Set-Cookie", f"alpha_gate_session={_session_value()}; Path=/; HttpOnly; SameSite=Strict")
                self.send_header("Location", "/")
                self.end_headers()
            else:
                self._send(401, LOGIN_HTML.encode(), "text/html; charset=utf-8")
            return
        if not self._require_auth():
            return
        payload = self._read_json()
        if path == "/api/paper/order":
            market_price = None
            if str(payload.get("order_type") or "LIMIT").upper() == "MARKET":
                quote = _quote(str(payload.get("symbol") or ""))
                market_price = quote.get("ltp") if isinstance(quote.get("ltp"), (int, float)) else None
            self._send_json(200, ENGINE.place_order(payload, market_price=market_price))
        elif path == "/api/paper/close":
            self._send_json(200, ENGINE.close_position(str(payload.get("position_id") or ""), float(payload.get("exit_price") or 0)))
        elif path == "/api/paper/reset":
            self._send_json(200, ENGINE.reset(payload.get("starting_balance")))
        elif path == "/api/paper/balance/add":
            self._send_json(200, ENGINE.add_balance(float(payload.get("amount") or 0)))
        else:
            self._send_json(404, {"status": "BLOCKED", "reason": "NOT_FOUND", "real_order": False, "go_live_allowed": False})

    def _read_json(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0") or 0)
            value = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
            return value if isinstance(value, dict) else {}
        except (ValueError, json.JSONDecodeError):
            return {}

    def _send_json(self, status: int, payload: Mapping[str, Any]) -> None:
        self._send(status, _json_bytes(payload), "application/json; charset=utf-8")

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return


def run() -> None:
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8080"))
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    run()
