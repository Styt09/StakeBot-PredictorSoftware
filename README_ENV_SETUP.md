# ALPHA-GATE X Environment Setup

This guide explains the safe configuration layer and read-only integrations.

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

## OpenAI read-only auditor variables

Phase 10 supports OpenAI as a read-only AI Safety Auditor and Error Doctor:

```env
OPENAI_API_KEY=
OPENAI_MODEL=gpt-5.1-mini
OPENAI_AUDITOR_ENABLED=true
OPENAI_AUTOFIX_ENABLED=false
AI_CAN_MODIFY_FILES=false
AI_CAN_PLACE_ORDERS=false
GO_LIVE_ALLOWED=false
```

Safety rules:

- `OPENAI_API_KEY` must stay backend-only and must never be shared in chat, screenshots, frontend code, logs, or Git commits.
- `OPENAI_AUTOFIX_ENABLED` stays `false`.
- `AI_CAN_MODIFY_FILES` stays `false`.
- `AI_CAN_PLACE_ORDERS` stays `false`.
- `GO_LIVE_ALLOWED` stays `false`.
- OpenAI can diagnose errors and audit signals, but cannot place broker orders, enable live trading, or fabricate missing market data.

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
OPENAI_AUTOFIX_ENABLED=false
AI_CAN_MODIFY_FILES=false
AI_CAN_PLACE_ORDERS=false
GO_LIVE_ALLOWED=false
```

PAPER and READ_ONLY should run even without Zerodha, database, Redis, or OpenAI credentials. Missing market data must show `DATA_UNAVAILABLE` and must not be fabricated.

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
