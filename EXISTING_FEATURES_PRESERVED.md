# Existing Features Preserved

This file lists existing app features that must not be deleted during incremental production-safety upgrades.

## Existing UI/pages to preserve
- Existing root dashboard at `/`.
- Existing ALPHA-GATE X shadow trading platform header/design.
- Existing Live Market Dashboard section.
- Existing Trading Terminal Signal section.
- Existing Real Live Trading Control Panel section.
- Existing Paper Trading Terminal section.
- Existing Future Institutional Modules section.
- Existing Real Shadow Runtime Status section.
- Existing candlestick canvas behavior.
- Existing watchlist behavior.
- Existing debug JSON expanders.
- Existing paper balance/order/status views.

## Existing APIs to preserve
GET:

- `/health`
- `/api/status`
- `/api/demo`
- `/api/shadow/status`
- `/api/live/readiness`
- `/api/live/orders`
- `/api/safety/gates`
- `/api/market/symbols`
- `/api/market/watchlist`
- `/api/market/quote`
- `/api/market/history`
- `/api/signal/live`
- `/api/signal/accuracy-report`
- `/api/paper/status`
- `/api/paper/statement`
- `/api/paper/settings`

POST:

- `/api/live/order/preview`
- `/api/live/order/submit`
- `/api/live/kill-switch`
- `/api/live/kill-switch/reset`
- `/api/paper/balance/add`
- `/api/paper/reset`
- `/api/paper/order`
- `/api/paper/position/close`
- `/api/paper/auto-trade/toggle`
- `/api/paper/settings`

## Existing trading behavior to preserve
- Missing market data must return `DATA_UNAVAILABLE`.
- Weak evidence must return `NO_TRADE` or non-actionable output.
- Real live order submit must remain fail-closed by default.
- Paper trading must remain virtual.
- `go_live_allowed` must remain false unless future audited gates explicitly pass.
- Existing Zerodha read-only quote/history behavior must remain backend-only.

## Existing implementation style to preserve
- Python package under `src/institutional_trading_platform`.
- Stdlib web app currently served from `web_app.py`.
- Pytest-based test suite.
- Docker/infrastructure scaffolding.
- Existing README and docs.

## Additive-change rule
New safety layers must be added through new modules, wrappers, docs, tests, or minimal endpoint extensions. Existing files should only be edited when needed for routing or safe compatibility.
