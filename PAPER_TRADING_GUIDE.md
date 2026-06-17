# PAPER TRADING GUIDE

## Verdict

- PAPER: READY CANDIDATE
- SHADOW: READY CANDIDATE
- LIVE: NO-GO
- go_live_allowed=false

## Purpose

Paper trading uses virtual money only. It is for workflow validation, risk-gate testing, UI validation, and operational evidence collection.

## What paper trading can do

- Read validated quote data.
- Create virtual paper orders.
- Block unsafe orders through risk checks.
- Track virtual open positions.
- Track virtual closed trades and P&L.
- Record evidence in audit logs.

## What paper trading cannot do

- It cannot place real Zerodha orders.
- It cannot guarantee real execution price.
- It cannot prove profitability.
- It cannot make the system live-ready.

## Safety rules

- Paper orders must pass central risk checks.
- Missing data must block orders.
- Weak signals must block orders.
- Persistent kill switch active must block orders.
- go_live_allowed must remain false.

## Useful endpoints

```text
GET  /api/paper/status
GET  /api/paper/statement
GET  /api/paper/orders
GET  /api/paper/trades
POST /api/paper/order
POST /api/paper/position/close
POST /api/paper/reset
POST /api/paper/balance/add
```

## Operational rule

Treat paper trading output as simulation evidence only. Before any future live consideration, paper output must be followed by 30 trading days of shadow validation.
