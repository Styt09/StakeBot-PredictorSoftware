# Missing Components for Real Trading Safety

This file lists missing or incomplete components required before any live-real-money readiness claim.

## Non-negotiable missing items

1. **Centralized config validation**
   - Canonical env names.
   - Safe defaults.
   - Secret masking.
   - Startup safety report.

2. **Formal trading mode system**
   - READ_ONLY, PAPER, SHADOW, LIVE_DISABLED, LIVE_ENABLED.
   - One source of truth for current mode.
   - UI badge and API endpoint.

3. **Market data safety layer**
   - Provider abstraction.
   - Data health states: CONNECTED, RECONNECTING, DISCONNECTED, STALE, DATA_UNAVAILABLE.
   - Latency/freshness checks.
   - Market open/closed check.
   - Stale data must block actionable signals/orders.

4. **Standard signal safety wrapper**
   - Normalized signal output format.
   - Confidence grade.
   - Expected move.
   - Data quality status.
   - Explicit blocked reasons.

5. **Central risk engine**
   - Must run before paper, shadow, and live orders.
   - Must include mode, market, data, signal, stop-loss, target, risk/reward, qty, positions, loss limits, cooldown, duplicate, kill switch, broker, drift checks.

6. **Persistent paper/shadow/live audit log**
   - Current paper state is in-memory.
   - Audit logs need persistence and filtering.

7. **Persistent kill switch**
   - Current kill switch behavior is not fully durable.
   - Must survive restart when database exists.

8. **Shadow trading evidence**
   - Live market data + theoretical orders + performance report.
   - Required before any live rollout.

9. **Broker adapter hardening**
   - Zerodha session lifecycle.
   - Token expiry handling.
   - Profile/margins/positions/orders/trades reconciliation.
   - place_order must refuse by default.

10. **Position reconciliation and drift detection**
    - Required before live orders.
    - Compare expected state vs broker ground truth.

11. **Database integration**
    - Durable orders, positions, logs, settings, kill switch, shadow runs.

12. **Authentication and access control**
    - Current local UI is not a production-authenticated trading console.

13. **Observability and alerts**
    - Structured logs.
    - Health endpoints.
    - Metrics.
    - Alerts for broker disconnect, data stale, kill switch, risk block.

14. **Deployment hardening**
    - Secrets manager.
    - TLS.
    - Monitoring.
    - Backups.
    - Restart/recovery tests.

## Current live-trading readiness
Final status: **NO-GO FOR LIVE TRADING**.

The app can be improved toward PAPER-READY and SHADOW-READY, but real live order execution must remain disabled until the above missing components are implemented, tested, and operationally validated.
