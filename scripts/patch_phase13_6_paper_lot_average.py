#!/usr/bin/env python3
"""Phase 13.6: Paper lot averaging + symbol search UI.

Safe paper-only patch:
- Adds lot-wise virtual BUY averaging for paper positions.
- Adds partial virtual SELL / lot reduction.
- Adds optional paper auto scale-in settings, with cooldown and max lots.
- Adds an easier stock search + paper trade cockpit UI.

This patch never enables live trading and does not place broker orders.
"""
from __future__ import annotations

from pathlib import Path
from time import time
import shutil

WEB_APP = Path("src/institutional_trading_platform/web_app.py")
BACKUP_DIR = Path(".alpha_gate_backups")
CSS_MARKER = "/* PHASE 13.6 PAPER LOT AVERAGING */"
HTML_MARKER = "<!-- PHASE 13.6 PAPER LOT AVERAGING UI -->"
JS_MARKER = "// PHASE 13.6 PAPER LOT AVERAGING HELPERS"

CSS = r'''
    /* PHASE 13.6 PAPER LOT AVERAGING */
    .lot-cockpit{margin:12px 0 16px;padding:14px;border-radius:22px;border:1px solid rgba(52,211,153,.30);background:linear-gradient(135deg,rgba(6,95,70,.22),rgba(14,165,233,.10));box-shadow:0 18px 54px rgba(0,0,0,.28)}
    .lot-cockpit h3{color:#bbf7d0}.lot-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(175px,1fr));gap:10px;margin-top:10px}.lot-card{padding:12px;border-radius:16px;background:rgba(2,6,23,.46);border:1px solid rgba(148,163,184,.20)}.lot-card strong{display:block;color:#67e8f9;font-size:.72rem;text-transform:uppercase;letter-spacing:.08em;margin-bottom:4px}.lot-actions{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-top:12px}.lot-buy{background:linear-gradient(135deg,rgba(5,150,105,.95),rgba(52,211,153,.28))!important}.lot-sell{background:linear-gradient(135deg,rgba(220,38,38,.90),rgba(251,113,133,.24))!important}.lot-copy{background:linear-gradient(135deg,rgba(37,99,235,.90),rgba(103,232,249,.28))!important}.lot-mini{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}.lot-mini button{width:auto;min-height:34px;padding:7px 11px;border-radius:999px}.lot-note{margin-top:10px;padding:10px;border-radius:14px;background:rgba(5,150,105,.12);border:1px solid rgba(52,211,153,.20);color:#d1fae5}.paper-row .lot-pill{display:inline-flex;margin:3px 4px 0 0;padding:4px 8px;border-radius:999px;background:rgba(103,232,249,.12);border:1px solid rgba(103,232,249,.20);font-size:.72rem;color:#dbeafe}.paper-search-panel{position:relative}.paper-suggestions{display:none;position:absolute;z-index:70;width:100%;max-height:250px;overflow:auto;background:#071523;border:1px solid rgba(103,232,249,.28);border-radius:14px;box-shadow:0 20px 60px rgba(0,0,0,.44);margin-top:4px}.paper-suggestion{padding:12px;border-bottom:1px solid rgba(148,163,184,.16);cursor:pointer}.paper-suggestion:hover{background:rgba(103,232,249,.12)}
'''

HTML = r'''
<!-- PHASE 13.6 PAPER LOT AVERAGING UI -->
<div class="lot-cockpit">
  <h3>Intraday Lot Averaging Cockpit · Paper Only</h3>
  <p class="muted">Jaise intraday me lot-wise BUY karte waqt average price change hota hai, yahan paper mode me same virtual concept hai: Buy More Lot se quantity add hogi aur average entry recalculate hoga. SELL se partial lot reduce/close hoga.</p>
  <div class="lot-grid">
    <div class="lot-card paper-search-panel"><strong>Stock Search</strong><input id="paper-symbol-search" value="RELIANCE" placeholder="Search stock for paper trade" oninput="queuePaperSymbolSearch(this.value)" onfocus="queuePaperSymbolSearch(this.value)" /><div id="paper-symbol-suggestions" class="paper-suggestions"></div></div>
    <div class="lot-card"><strong>Lot Quantity</strong><input id="paper-lot-qty" type="number" value="1" min="1" onchange="setPaperQty(this.value)" /></div>
    <div class="lot-card"><strong>Average Concept</strong><span>New Avg = total virtual cost / total quantity</span></div>
    <div class="lot-card"><strong>Safety</strong><span>Virtual only · LIVE NO-GO · go_live_allowed=false</span></div>
  </div>
  <div class="lot-actions">
    <button class="lot-copy" onclick="copyCurrentMarketToPaper()">Copy Selected Stock + LTP</button>
    <button class="lot-copy" onclick="copySignalToPaperSafe()">Copy Signal SL/Targets</button>
    <button class="lot-buy" onclick="paperBuyMoreLot()">Buy More Lot / Average</button>
    <button class="lot-sell" onclick="paperSellLot()">Sell Lot / Partial Exit</button>
  </div>
  <div class="lot-mini"><button onclick="setLotQty(1)">Lot 1</button><button onclick="setLotQty(5)">Lot 5</button><button onclick="setLotQty(10)">Lot 10</button><button onclick="setLotQty(25)">Lot 25</button></div>
  <div class="lot-note">Auto mode me scale-in default OFF hai. Safety ke liye max lots/cooldown ke bina auto add nahi karega.</div>
  <div class="controls"><div class="field"><label>Auto scale-in</label><select id="setting-scale-auto"><option value="false">OFF</option><option value="true">ON</option></select></div><div class="field"><label>Max lots per symbol</label><input id="setting-max-lots" type="number" value="6" min="1" /></div><div class="field"><label>Avg-down trigger %</label><input id="setting-scale-move" type="number" value="0.35" min="0" step="0.05" /></div><div class="field"><label>Scale cooldown seconds</label><input id="setting-scale-cooldown" type="number" value="300" min="60" /></div></div>
</div>
'''

JS = r'''
// PHASE 13.6 PAPER LOT AVERAGING HELPERS
let paperSymbolSearchTimer=null;
function setLotQty(q){document.getElementById('paper-lot-qty').value=String(q);setPaperQty(q)}
function setPaperQty(q){const qty=Math.max(1,Number(q||1));const a=document.getElementById('paper-qty');const b=document.getElementById('paper-lot-qty');if(a)a.value=String(qty);if(b)b.value=String(qty)}
function queuePaperSymbolSearch(q){clearTimeout(paperSymbolSearchTimer);paperSymbolSearchTimer=setTimeout(()=>paperSymbolSearch(q),220)}
function paperSymbolSearch(q){q=(q||'').trim().toUpperCase();const box=document.getElementById('paper-symbol-suggestions');if(!box)return;if(q.length<1){box.style.display='none';box.innerHTML='';return}fetch('/api/market/symbols?q='+encodeURIComponent(q)).then(r=>r.json()).then(p=>{const symbols=p.symbols||[];box.innerHTML=symbols.slice(0,50).map(s=>`<div class="paper-suggestion" onclick="pickPaperSymbol('${s}')">${s}</div>`).join('');box.style.display=symbols.length?'block':'none'}).catch(()=>{box.style.display='none';box.innerHTML=''})}
function pickPaperSymbol(symbol){symbol=(symbol||'RELIANCE').trim().toUpperCase();document.getElementById('paper-symbol-search').value=symbol;document.getElementById('paper-symbol').value=symbol;selectMarketSymbol(symbol);const box=document.getElementById('paper-symbol-suggestions');if(box){box.style.display='none';box.innerHTML=''}}
function currentLtpNumber(){const raw=(document.getElementById('quote-ltp')?.textContent||'').replace(/[^0-9.\-]/g,'');const n=Number(raw);return Number.isFinite(n)?n:0}
function copyCurrentMarketToPaper(){const symbol=(document.getElementById('market-symbol')?.value||document.getElementById('paper-symbol-search')?.value||'RELIANCE').trim().toUpperCase();document.getElementById('paper-symbol-search').value=symbol;document.getElementById('paper-symbol').value=symbol;const ltp=currentLtpNumber();if(ltp>0)document.getElementById('paper-entry').value=ltp.toFixed(2);document.getElementById('paper-order-result').textContent='Copied selected stock and latest LTP to paper form. Virtual only.'}
function copySignalToPaperSafe(){try{const raw=document.getElementById('signal-raw')?.textContent||'{}';const p=JSON.parse(raw);copyCurrentMarketToPaper();if(p.decision)document.getElementById('paper-side').value=p.decision==='SELL'?'SELL':'BUY';if(p.entry)document.getElementById('paper-entry').value=Number(p.entry).toFixed(2);if(p.stop_loss)document.getElementById('paper-sl').value=Number(p.stop_loss).toFixed(2);if(p.target_1)document.getElementById('paper-t1').value=Number(p.target_1).toFixed(2);if(p.target_2)document.getElementById('paper-t2').value=Number(p.target_2).toFixed(2);document.getElementById('paper-order-result').textContent='Signal copied to paper form. Review before virtual trade.'}catch(e){document.getElementById('paper-order-result').textContent='Signal copy failed: '+e}}
function paperBuyMoreLot(){copyCurrentMarketToPaper();document.getElementById('paper-side').value='BUY';setPaperQty(document.getElementById('paper-lot-qty').value);submitPaperOrder()}
function paperSellLot(){copyCurrentMarketToPaper();document.getElementById('paper-side').value='SELL';setPaperQty(document.getElementById('paper-lot-qty').value);submitPaperOrder()}
const __phase136SettingsPayload=settingsPayload;settingsPayload=function(){const p=__phase136SettingsPayload();p.auto_scale_in_enabled=document.getElementById('setting-scale-auto')?.value==='true';p.max_lots_per_symbol=Number(document.getElementById('setting-max-lots')?.value||6);p.scale_in_price_improvement_percent=Number(document.getElementById('setting-scale-move')?.value||0.35);p.scale_cooldown_seconds=Number(document.getElementById('setting-scale-cooldown')?.value||300);return p};
const __phase136LoadPaperSettings=loadPaperSettings;loadPaperSettings=function(){fetch('/api/paper/settings?symbol='+encodeURIComponent(document.getElementById('market-symbol').value)).then(r=>r.json()).then(p=>{const s=p.settings||p;document.getElementById('setting-auto').value=String(!!s.paper_auto_trade_enabled);document.getElementById('setting-sizing').value=s.sizing_mode;document.getElementById('setting-fixed-qty').value=s.fixed_quantity;document.getElementById('setting-fixed-amount').value=s.fixed_amount;document.getElementById('setting-target-mode').value=s.target_mode;document.getElementById('setting-target-value').value=s.target_value;document.getElementById('setting-sl-mode').value=s.stop_loss_mode;document.getElementById('setting-sl-value').value=s.stop_loss_value;document.getElementById('setting-max-open').value=s.max_open_positions;document.getElementById('setting-max-trades').value=s.max_trades_per_day;document.getElementById('setting-max-loss').value=s.max_daily_loss;if(document.getElementById('setting-scale-auto'))document.getElementById('setting-scale-auto').value=String(!!s.auto_scale_in_enabled);if(document.getElementById('setting-max-lots'))document.getElementById('setting-max-lots').value=s.max_lots_per_symbol??6;if(document.getElementById('setting-scale-move'))document.getElementById('setting-scale-move').value=s.scale_in_price_improvement_percent??0.35;if(document.getElementById('setting-scale-cooldown'))document.getElementById('setting-scale-cooldown').value=s.scale_cooldown_seconds??300;renderKv('paper-auto-preview',p.auto_trade_preview||{},['selected_symbol','latest_ltp','state','sizing_mode','calculated_quantity','entry_price','position_lots','average_entry','max_lots_per_symbol','auto_scale_in_enabled','block_reasons']);document.getElementById('paper-settings-raw').textContent=JSON.stringify(p,null,2)})}
loadPaperStatus=function(isAuto=false){fetch('/api/paper/status').then(r=>r.json()).then(p=>{renderKv('paper-summary',p.account_summary,['mode','cash_balance','equity','realized_pnl','unrealized_pnl','open_position_count','closed_trade_count','win_rate','paper_auto_trade_state','go_live_allowed']);document.getElementById('paper-open-positions').innerHTML=(p.open_positions||[]).map(pos=>{const lots=(pos.lots||[]).map((l,i)=>`<span class="lot-pill">Lot ${i+1}: ${l.quantity} @ ${l.price}</span>`).join('');return `<div class="paper-row"><strong>${pos.symbol} ${pos.side} x${pos.quantity}</strong><br>Avg Entry ${pos.entry_price} · LTP ${pos.last_price??'DATA_UNAVAILABLE'} · Lots ${pos.lot_count??(pos.lots||[]).length||1} · P&L <span class="${Number(pos.unrealized_pnl||0)>=0?'profit':'loss'}">${pos.unrealized_pnl}</span><br>SL ${pos.stop_loss} · T1 ${pos.target_1} · T2 ${pos.target_2}<br>${lots}<br><button onclick="closePaperPosition('${pos.position_id}')">Manual Full Exit</button></div>`}).join('')||'No open paper positions.';document.getElementById('paper-closed-trades').innerHTML=(p.closed_trades||[]).slice(-10).reverse().map(t=>`<div class="paper-row"><strong>${t.symbol} ${t.exit_reason}</strong><br>Qty ${t.quantity} · Avg Entry ${t.entry_price} → Exit ${t.exit_price} · P&L <span class="${Number(t.pnl||0)>=0?'profit':'loss'}">${t.pnl}</span></div>`).join('')||'No closed paper trades.';document.getElementById('paper-ledger').innerHTML=(p.statement_ledger||[]).slice(-10).reverse().map(e=>`<div class="paper-row"><strong>${e.event}</strong><br>${e.timestamp}<br>${e.message}</div>`).join('')||'No ledger entries yet.';if(!isAuto)document.getElementById('paper-raw').textContent=JSON.stringify(p,null,2)})}
'''

NEW_PAPER_ORDER = r'''def _paper_order(payload: Mapping[str, Any]) -> dict[str, Any]:
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
            return {"status": "BLOCKED", "reason": "no matching long paper position found for partial/full SELL", "go_live_allowed": False}
        return _paper_reduce_or_close_position(open_long["position_id"], quantity, price, "MANUAL_LOT_SELL", source)
    return {"status": "BLOCKED", "reason": "side must be BUY or SELL", "go_live_allowed": False}

'''

NEW_OPEN_LONG = r'''def _paper_open_long(symbol: str, quantity: int, price: float, payload: Mapping[str, Any], source: str, *, event: str) -> dict[str, Any]:
    cost = round(price * quantity, 2)
    if float(_PAPER.get("cash_balance", 0.0)) < cost:
        return {"status": "BLOCKED", "reason": "INSUFFICIENT_PAPER_BALANCE", "required_cash": cost, "cash_balance": _PAPER.get("cash_balance", 0.0), "go_live_allowed": False}

    existing = next((p for p in _PAPER.get("open_positions", []) if p["symbol"] == symbol and p["side"] == "BUY"), None)
    if existing is not None:
        lots = list(existing.get("lots") or [{"quantity": int(existing["quantity"]), "price": float(existing["entry_price"]), "timestamp": existing.get("opened_at"), "source": existing.get("data_source")}])
        max_lots = max(1, _safe_int(_PAPER_SETTINGS.get("max_lots_per_symbol"), 6))
        if len(lots) >= max_lots:
            return {"status": "BLOCKED", "reason": "MAX_LOTS_PER_SYMBOL_REACHED", "max_lots_per_symbol": max_lots, "go_live_allowed": False}
        if event == "PAPER_AUTO_BUY":
            cooldown = max(60, _safe_int(_PAPER_SETTINGS.get("scale_cooldown_seconds"), 300))
            last_scale = str(existing.get("last_scale_at") or existing.get("opened_at") or "")
            try:
                age = (datetime.now(UTC) - datetime.fromisoformat(last_scale.replace("Z", "+00:00"))).total_seconds()
            except Exception:
                age = cooldown + 1
            if age < cooldown:
                return {"status": "BLOCKED", "reason": "AUTO_SCALE_COOLDOWN_ACTIVE", "cooldown_seconds": cooldown, "age_seconds": round(age, 1), "go_live_allowed": False}
        old_qty = int(existing["quantity"])
        old_avg = float(existing["entry_price"])
        new_qty = old_qty + quantity
        new_avg = round(((old_qty * old_avg) + (quantity * price)) / new_qty, 2)
        lots.append({"quantity": quantity, "price": round(price, 2), "timestamp": _now(), "source": source, "event": event})
        existing.update({"quantity": new_qty, "entry_price": new_avg, "average_price": new_avg, "lot_count": len(lots), "lots": lots, "last_price": round(price, 2), "last_scale_at": _now(), "unrealized_pnl": round((price - new_avg) * new_qty, 2), "data_source": source, "go_live_allowed": False})
        for key in ("stop_loss", "target_1", "target_2"):
            value = round(_safe_float(payload.get(key), 0.0), 2)
            if value > 0:
                existing[key] = value
        _PAPER["cash_balance"] = round(float(_PAPER.get("cash_balance", 0.0)) - cost, 2)
        event_name = "PAPER_AVERAGE_DOWN" if price < old_avg else "PAPER_AVERAGE_UP" if price > old_avg else "PAPER_ADD_LOT"
        _paper_ledger(event_name, f"Added virtual lot {quantity} {symbol} @ {price:.2f}; avg {old_avg:.2f} -> {new_avg:.2f}", position_id=existing["position_id"], symbol=symbol, quantity=quantity, price=price, average_price=new_avg, lot_count=len(lots))
        return {"status": "PASS", "message": "virtual lot added and average price recalculated", "paper_order": existing, "paper_status": _paper_status(), "go_live_allowed": False}

    position = {"position_id": f"paper-{uuid4()}", "symbol": symbol, "side": "BUY", "quantity": quantity, "entry_price": round(price, 2), "average_price": round(price, 2), "lot_count": 1, "lots": ({"quantity": quantity, "price": round(price, 2), "timestamp": _now(), "source": source, "event": event},), "stop_loss": round(_safe_float(payload.get("stop_loss"), 0.0), 2), "target_1": round(_safe_float(payload.get("target_1"), 0.0), 2), "target_2": round(_safe_float(payload.get("target_2"), 0.0), 2), "opened_at": _now(), "data_source": source, "status": "OPEN", "last_price": round(price, 2), "unrealized_pnl": 0.0, "go_live_allowed": False}
    _PAPER["cash_balance"] = round(float(_PAPER.get("cash_balance", 0.0)) - cost, 2)
    _PAPER.setdefault("open_positions", []).append(position)
    _paper_ledger(event, f"Opened virtual BUY {quantity} {symbol} @ {price:.2f}", position_id=position["position_id"], symbol=symbol, quantity=quantity, price=price)
    return {"status": "PASS", "paper_order": position, "paper_status": _paper_status(), "go_live_allowed": False}

'''

REDUCE_HELPER = r'''def _paper_reduce_or_close_position(position_id: str, sell_quantity: int, exit_price: float, exit_reason: str, source: str) -> dict[str, Any]:
    position = _paper_find_position(position_id)
    if position is None:
        return {"status": "BLOCKED", "reason": "position_id not found", "go_live_allowed": False}
    current_qty = int(position["quantity"])
    if sell_quantity <= 0:
        return {"status": "BLOCKED", "reason": "sell quantity must be positive", "go_live_allowed": False}
    if sell_quantity > current_qty:
        return {"status": "BLOCKED", "reason": "sell quantity exceeds open paper quantity", "open_quantity": current_qty, "requested_quantity": sell_quantity, "go_live_allowed": False}
    if sell_quantity == current_qty:
        return _paper_close_position(position_id, exit_price, exit_reason, source)

    entry = float(position["entry_price"])
    pnl = round((exit_price - entry) * sell_quantity, 2)
    proceeds = round(exit_price * sell_quantity, 2)
    _PAPER["cash_balance"] = round(float(_PAPER.get("cash_balance", 0.0)) + proceeds, 2)
    remaining_qty = current_qty - sell_quantity
    position["quantity"] = remaining_qty
    position["last_price"] = round(exit_price, 2)
    position["unrealized_pnl"] = round((exit_price - entry) * remaining_qty, 2)
    trade = {**position, "quantity": sell_quantity, "remaining_quantity": remaining_qty, "status": "PARTIAL_CLOSED", "exit_price": round(exit_price, 2), "exit_reason": exit_reason, "closed_at": _now(), "pnl": pnl, "data_source": source, "go_live_allowed": False}
    _PAPER.setdefault("closed_trades", []).append(trade)
    _paper_ledger(exit_reason, f"Partially sold virtual {sell_quantity} {position['symbol']} @ {exit_price:.2f}; remaining {remaining_qty}; P&L {pnl:.2f}", position_id=position_id, symbol=position["symbol"], quantity=sell_quantity, remaining_quantity=remaining_qty, pnl=pnl)
    return {"status": "PASS", "partial_trade": trade, "paper_status": _paper_status(), "go_live_allowed": False}

'''

NEW_AUTO_PLAN = r'''def _paper_auto_trade_plan(symbol: str, signal: Mapping[str, Any] | None) -> dict[str, Any]:
    symbol = (symbol or "RELIANCE").upper()
    settings = _PAPER_SETTINGS
    quote = _LAST_QUOTES.get(symbol)
    entry = float(quote["ltp"]) if quote and quote.get("validation_status") == "VALIDATED" and isinstance(quote.get("ltp"), (int, float)) else 0.0
    quantity = int(settings["fixed_quantity"]) if settings["sizing_mode"] == "FIXED_QUANTITY" else int(float(settings["fixed_amount"]) // entry) if entry > 0 else 0
    target_1, target_2, stop_loss = _paper_generated_exits(entry)
    existing = next((p for p in _PAPER.get("open_positions", []) if p["symbol"] == symbol and p["side"] == "BUY"), None)
    position_lots = int(existing.get("lot_count", len(existing.get("lots", [])) or 1)) if existing else 0
    average_entry = float(existing.get("entry_price", 0.0)) if existing else 0.0
    reasons: list[str] = []
    if not settings["paper_auto_trade_enabled"]: reasons.append("PAPER_AUTO_TRADE_OFF")
    if signal is not None:
        if signal.get("decision") != "BUY": reasons.append("SIGNAL_NOT_BUY")
        if signal.get("validation_status") != "VALIDATED": reasons.append("SIGNAL_NOT_VALIDATED")
        if _safe_float(signal.get("confidence_score"), 0.0) < 75: reasons.append("CONFIDENCE_BELOW_75")
        if _safe_float(signal.get("risk_reward"), 0.0) < 2: reasons.append("RISK_REWARD_BELOW_2")
    if quote is None or quote.get("validation_status") != "VALIDATED": reasons.append("VALIDATED_QUOTE_UNAVAILABLE")
    if _kill_switch_active(): reasons.append("KILL_SWITCH_ENABLED")
    if _paper_trades_today() >= int(settings["max_trades_per_day"]): reasons.append("MAX_TRADES_PER_DAY_REACHED")
    if _paper_daily_loss() >= float(settings["max_daily_loss"]): reasons.append("MAX_DAILY_LOSS_REACHED")
    if quantity < 1: reasons.append("INSUFFICIENT_PAPER_AMOUNT")
    if entry > 0 and quantity * entry > float(_PAPER.get("cash_balance", 0.0)): reasons.append("INSUFFICIENT_PAPER_BALANCE")
    if existing is None:
        if len(_PAPER.get("open_positions", [])) >= int(settings["max_open_positions"]): reasons.append("MAX_OPEN_POSITIONS_REACHED")
    else:
        if not bool(settings.get("auto_scale_in_enabled", False)): reasons.append("AUTO_SCALE_IN_OFF")
        max_lots = max(1, _safe_int(settings.get("max_lots_per_symbol"), 6))
        if position_lots >= max_lots: reasons.append("MAX_LOTS_PER_SYMBOL_REACHED")
        trigger = max(0.0, _safe_float(settings.get("scale_in_price_improvement_percent"), 0.35))
        required_price = average_entry * (1 - trigger / 100) if average_entry else 0.0
        if required_price and entry > required_price: reasons.append("SCALE_IN_PRICE_NOT_IMPROVED")
    state = "ARMED" if not reasons else "OFF" if reasons == ["PAPER_AUTO_TRADE_OFF"] else "BLOCKED"
    return {"state": state, "selected_symbol": symbol, "latest_ltp": round(entry, 2) if entry else DATA_UNAVAILABLE, "sizing_mode": settings["sizing_mode"], "calculated_quantity": quantity, "fixed_amount": settings["fixed_amount"], "fixed_quantity": settings["fixed_quantity"], "entry_price": round(entry, 2) if entry else DATA_UNAVAILABLE, "generated_stop_loss": stop_loss, "generated_target_1": target_1, "generated_target_2": target_2, "position_lots": position_lots, "average_entry": round(average_entry, 2) if average_entry else DATA_UNAVAILABLE, "max_lots_per_symbol": settings.get("max_lots_per_symbol", 6), "auto_scale_in_enabled": bool(settings.get("auto_scale_in_enabled", False)), "block_reasons": tuple(dict.fromkeys(reasons)), "go_live_allowed": False}

'''


def replace_function(text: str, name: str, replacement: str, next_name: str) -> str:
    start = text.find(f"def {name}(")
    if start < 0:
        raise SystemExit(f"Function {name} not found")
    end = text.find(f"def {next_name}(", start)
    if end < 0:
        raise SystemExit(f"Next function {next_name} not found after {name}")
    return text[:start] + replacement + text[end:]


def main() -> None:
    if not WEB_APP.exists():
        raise SystemExit(f"Missing file: {WEB_APP}")
    BACKUP_DIR.mkdir(exist_ok=True)
    backup = BACKUP_DIR / f"web_app_before_phase13_6_lot_average_{int(time())}.py"
    shutil.copy2(WEB_APP, backup)
    text = WEB_APP.read_text(encoding="utf-8")

    if '"max_lots_per_symbol"' not in text:
        text = text.replace('    "max_daily_loss": 1000.0,\n', '    "max_daily_loss": 1000.0,\n    "max_lots_per_symbol": 6,\n    "auto_scale_in_enabled": False,\n    "scale_in_price_improvement_percent": 0.35,\n    "scale_cooldown_seconds": 300,\n', 1)

    if '"max_lots_per_symbol"] = max(1' not in text:
        text = text.replace('    _PAPER_SETTINGS["max_daily_loss"] = max(0.0, _safe_float(payload.get("max_daily_loss", _PAPER_SETTINGS["max_daily_loss"]), 1000.0))\n', '    _PAPER_SETTINGS["max_daily_loss"] = max(0.0, _safe_float(payload.get("max_daily_loss", _PAPER_SETTINGS["max_daily_loss"]), 1000.0))\n    _PAPER_SETTINGS["max_lots_per_symbol"] = max(1, _safe_int(payload.get("max_lots_per_symbol", _PAPER_SETTINGS.get("max_lots_per_symbol", 6)), 6))\n    _PAPER_SETTINGS["auto_scale_in_enabled"] = bool(payload.get("auto_scale_in_enabled", _PAPER_SETTINGS.get("auto_scale_in_enabled", False)))\n    _PAPER_SETTINGS["scale_in_price_improvement_percent"] = max(0.0, _safe_float(payload.get("scale_in_price_improvement_percent", _PAPER_SETTINGS.get("scale_in_price_improvement_percent", 0.35)), 0.35))\n    _PAPER_SETTINGS["scale_cooldown_seconds"] = max(60, _safe_int(payload.get("scale_cooldown_seconds", _PAPER_SETTINGS.get("scale_cooldown_seconds", 300)), 300))\n', 1)

    text = replace_function(text, "_paper_auto_trade_plan", NEW_AUTO_PLAN, "_paper_generated_exits")
    text = replace_function(text, "_paper_order", NEW_PAPER_ORDER, "_paper_position_close")
    text = replace_function(text, "_paper_open_long", NEW_OPEN_LONG + REDUCE_HELPER, "_paper_close_position")

    if CSS_MARKER not in text:
        text = text.replace("  </style>", CSS + "\n  </style>", 1)
    if HTML_MARKER not in text:
        text = text.replace("<h2>Paper Trading Terminal</h2>", "<h2>Paper Trading Terminal</h2>" + HTML, 1)
    if JS_MARKER not in text:
        text = text.replace("fetch('/api/market/symbols?q=')", JS + "\nfetch('/api/market/symbols?q=')", 1)

    WEB_APP.write_text(text, encoding="utf-8")
    print("✅ Phase 13.6 paper lot averaging applied")
    print("✅ Manual paper BUY now averages lots for same symbol")
    print("✅ Manual paper SELL can partially reduce lots")
    print("✅ Auto scale-in settings added with max lots + cooldown")
    print("✅ Paper stock search and lot cockpit UI added")
    print("✅ LIVE remains NO-GO / go_live_allowed=false")
    print(f"Backup: {backup}")


if __name__ == "__main__":
    main()
