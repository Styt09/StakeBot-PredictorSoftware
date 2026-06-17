# Live Trading NO-GO Reasons

Current verdict: **NO-GO FOR REAL LIVE TRADING**.

Real live order placement must remain disabled. The app may be used for read-only market data, signal review, paper trading, and staged shadow testing only.

## Current NO-GO reasons

1. **No complete centralized risk engine**
   - Some checks exist, but all order paths need one mandatory risk engine.

2. **No durable database-backed state**
   - Paper positions, settings, audit logs, and kill switch state need persistence.

3. **No completed shadow trading probation**
   - Live market theoretical orders and performance must be tracked before live rollout.

4. **No broker reconciliation loop**
   - Broker positions/orders/trades must be reconciled against internal expected state.

5. **No proven position drift handling**
   - Any broker/internal mismatch must block trading.

6. **Market data freshness not fully centralized**
   - Stale/missing data must block signals and all order paths.

7. **No production authentication/authorization**
   - Trading console must not be exposed without access control.

8. **Secrets exposure risk during development**
   - Zerodha credentials/tokens have been visible in screenshots. Rotate all exposed secrets/tokens before continuing.

9. **No production-grade observability**
   - Metrics, alerts, and incident response need implementation.

10. **No compliance/operational approval**
    - Real-money automation requires human approval, broker terms review, and operational runbooks.

11. **No live stop-loss/target broker-side management**
    - Paper SL/target behavior is not equal to real broker-side protection.

12. **No disaster recovery proof**
    - Crash/restart behavior must prove no duplicate orders and no position drift.

## Required before LIMITED-LIVE-READY

- Trading mode API and UI status.
- Central risk engine enforcing all order paths.
- Persistent kill switch.
- Persistent audit log.
- Shadow mode report.
- Broker connection health endpoint.
- Broker reconciliation.
- Manual approval gate.
- One-symbol, one-quantity controlled rollout plan.

## Safety rule
Until these are complete, any live order endpoint must return `BLOCKED`, and `go_live_allowed` must remain `false`.
