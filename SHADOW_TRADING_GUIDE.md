# SHADOW TRADING GUIDE

## Verdict

- PAPER: READY CANDIDATE
- SHADOW: READY CANDIDATE
- LIVE: NO-GO
- go_live_allowed=false

## Purpose

Shadow trading observes live market data and creates theoretical orders only. It is the required bridge between paper validation and any future live review.

## Shadow trading rules

- No real Zerodha order submission.
- Theoretical fills must use validated quote/LTP only.
- Missing or stale data must block shadow evaluation.
- Safe signal must be actionable.
- Risk engine must approve.
- Persistent kill switch must be inactive.
- go_live_allowed=false always.

## Useful endpoints

```text
GET  /api/shadow/status
GET  /api/shadow/orders
GET  /api/shadow/trades
GET  /api/shadow/report
POST /api/shadow/evaluate
POST /api/shadow/reset
```

## Required evidence before live review

Collect at least 30 trading days of shadow records including theoretical orders, blocked reasons, market data health, signal output, risk output, broker health, kill-switch events, and audit reports.

## Shadow readiness is not live readiness

Even if SHADOW is READY CANDIDATE, LIVE remains NO-GO until broker reconciliation, zero drift, persistent storage, monitoring, compliance, and human approval are complete.
