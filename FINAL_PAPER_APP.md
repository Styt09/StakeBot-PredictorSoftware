# Final Paper Trading Website / PWA

This is the clean deployment entry for virtual paper trading:

```bash
python -m institutional_trading_platform.paper_web_app
```

Open:

```text
http://127.0.0.1:8080
```

## What is fixed

- One UI and one API contract; no injected duplicate JavaScript handlers.
- SQLite persistence for account, open positions, trades, and ledger.
- LIMIT orders always honor the typed limit price.
- MARKET orders fail closed when a validated Zerodha quote is unavailable.
- BUY opens a long or covers an existing short.
- SELL closes an existing long or opens a new MIS short.
- CNC short opening is blocked with `CNC_SHORT_NOT_ALLOWED`.
- MIS uses 20% virtual margin; CNC uses full virtual cash.
- Exact block reasons are returned to the UI.
- `real_order=false` and `go_live_allowed=false` remain enforced.
- Installable PWA shell with service worker.
- Optional passcode protection through `APP_ACCESS_TOKEN`.

## Local run

```bash
python -m pip install -e .
export APP_ACCESS_TOKEN='choose-a-long-private-passcode'
export PAPER_DB_PATH='data/paper_trading.db'
export HOST='0.0.0.0'
export PORT='8080'
python -m institutional_trading_platform.paper_web_app
```

Zerodha read-only quote variables:

```bash
export ZERODHA_API_KEY='...'
export ZERODHA_ACCESS_TOKEN='...'
```

Do not commit these values. The Zerodha access token still follows Zerodha's normal session-expiry rules.

## Docker website run

```bash
docker build -t alpha-gate-paper .
docker run --rm \
  -p 8080:8080 \
  -e APP_ACCESS_TOKEN='choose-a-long-private-passcode' \
  -e ZERODHA_API_KEY='...' \
  -e ZERODHA_ACCESS_TOKEN='...' \
  -v "$PWD/paper-data:/app/data" \
  alpha-gate-paper
```

## Public hosting

Deploy the repository as a Docker web service. Configure:

```text
PORT=8080
HOST=0.0.0.0
PAPER_DB_PATH=/persistent-data/paper_trading.db
APP_ACCESS_TOKEN=<long private passcode>
ZERODHA_API_KEY=<backend secret>
ZERODHA_ACCESS_TOKEN=<backend secret>
REAL_BROKER_ORDER_SUBMIT_ENABLED=false
GO_LIVE_ALLOWED=false
```

Attach a persistent disk to the directory containing `PAPER_DB_PATH`. Without a persistent disk, paper positions will be lost when a cloud instance is recreated.

## Install as an app

After HTTPS deployment:

- iPhone/iPad: Safari → Share → **Add to Home Screen**.
- Android/Chrome: menu → **Install app** or **Add to Home screen**.

This installs the PWA shell. It does not enable real broker execution.
