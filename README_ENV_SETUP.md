# ALPHA-GATE X Environment Setup

This guide explains the safe Phase 1 configuration layer.

## Create local `.env`

```bash
cp .env.example .env
```

Fill only the values needed for local development. Do not commit `.env`.

## Core variables

- `APP_ENV`: app environment. Use `development` locally.
- `TRADING_MODE`: one of `READ_ONLY`, `PAPER`, `SHADOW`, `LIVE_DISABLED`, `LIVE_ENABLED`.
- `ENABLE_LIVE_TRADING`: must stay `false` unless a future audited live phase explicitly enables it.
- `DATABASE_URL`: optional in PAPER/READ_ONLY. Required before LIVE_ENABLED can even be considered.
- `REDIS_URL`: optional in PAPER/READ_ONLY.
- `MARKET_TIMEZONE`: default `Asia/Kolkata`.
- `LOG_LEVEL`: default `info`.

## Zerodha variables

- `ZERODHA_API_KEY`
- `ZERODHA_API_SECRET`
- `ZERODHA_REDIRECT_URL`
- `ZERODHA_ACCESS_TOKEN`
- `ZERODHA_USER_ID`

These values are backend-only. Never place Zerodha secret or access token in frontend code, screenshots, browser local storage, or public logs.

## Risk limits

- `MAX_DAILY_LOSS`: safe default 1000.
- `MAX_TRADE_LOSS`: safe default 250.
- `MAX_OPEN_POSITIONS`: safe default 2.
- `MAX_QTY_PER_ORDER`: safe default 1.
- `MIN_SIGNAL_CONFIDENCE`: safe default 70.
- `MIN_RISK_REWARD`: safe default 1.5.

## Trading modes

- `READ_ONLY`: market data and system review only.
- `PAPER`: virtual paper trading only. Default mode.
- `SHADOW`: theoretical trading on market data, no real broker orders.
- `LIVE_DISABLED`: live trading intentionally blocked.
- `LIVE_ENABLED`: future gated mode only. It must be rejected unless all safety requirements are complete.

## Live trading default

Live trading is disabled by default because the system still needs persistent storage, full risk engine enforcement, shadow trading evidence, broker reconciliation, authentication, monitoring, and security hardening.

## Safe local development

Recommended local values:

```env
APP_ENV=development
TRADING_MODE=PAPER
ENABLE_LIVE_TRADING=false
MARKET_TIMEZONE=Asia/Kolkata
LOG_LEVEL=info
```

PAPER and READ_ONLY should run even without Zerodha, database, or Redis credentials. Missing market data must show `DATA_UNAVAILABLE` and must not be fabricated.

## Required before live trading can be considered

Before `LIVE_ENABLED` can even be reviewed, the following must exist and pass tests:

- `ENABLE_LIVE_TRADING=true` only in a controlled environment.
- Complete Zerodha backend credentials.
- Database configured and migration-tested.
- Central risk engine.
- Persistent kill switch.
- Persistent audit logs.
- Shadow trading report.
- Broker health and reconciliation.
- Manual approval and runbook.
- No exposed secrets.

Current verdict remains: **NO-GO for real live trading**.
