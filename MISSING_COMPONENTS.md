# Missing Components for Real Trading Safety

This file lists missing or incomplete components required before any live-real-money readiness claim.

## Phase 1 config status

Phase 1 added a safe configuration module, secret masking, safe public config structure, `.env.example`, environment setup docs, and config tests. The remaining config-related gap is wiring the public config endpoint into the local `web_app.py` route in environments where local uncommitted changes block merge/pull.

## Non-negotiable missing items

1. **Formal trading mode system**
   - READ_ONLY, PAPER, SHADOW, LIVE_DISABLED, LIVE_ENABLED exist in the config module.
   - Still needs full UI badge and existing dashboard endpoint wiring.

2. **Market data safety layer**
   - Provider abstraction.
   - Data health states: CONNECTED, RECONNECTING, DISCONNECTED, STALE, DATA_UNAVAILABLE.
   - Latency/freshness checks.
   - Market open/closed check.
   - Stale data must block actionable signals/orders.

3. **Standard signal safety wrapper**
   - Normalized signal output format.
   - Confidence grade.
   - Expected move.
   - Data quality status.
   - Explicit blocked reasons.

4. **Central risk engine**
   - Must run before paper, shadow, and live orders.
   - Must include mode, market, data, signal, stop-loss, target, risk/reward, qty, positions, loss limits, cooldown, duplicate, kill switch, broker, drift checks.

5. **Persistent paper/shadow/live audit log**
   - Current paper state is in-memory.
   - Audit logs need persistence and filtering.

6. **Persistent kill switch**
   - Current kill switch behavior is not fully durable.
   - Must survive restart when database exists.

7. **Shadow trading evidence**
   - Live market data + theoretical orders + performance report.
   - Required before any live rollout.

8. **Broker adapter hardening**
   - Zerodha session lifecycle.
   - Token expiry handling.
   - Profile/margins/positions/orders/trades reconciliation.
   - place_order must refuse by default.

9. **Position reconciliation and drift detection**
   - Required before live orders.
   - Compare expected state vs broker ground truth.

10. **Database integration**
    - Durable orders, positions, logs, settings, kill switch, shadow runs.

11. **Authentication and access control**
    - Current local UI is not a production-authenticated trading console.

12. **Observability and alerts**
    - Structured logs.
    - Health endpoints.
    - Metrics.
    - Alerts for broker disconnect, data stale, kill switch, risk block.

13. **Deployment hardening**
    - Secrets manager.
    - TLS.
    - Monitoring.
    - Backups.
    - Restart/recovery tests.

## Current live-trading readiness

Final status: **NO-GO FOR LIVE TRADING**.

The app can be improved toward PAPER-READY and SHADOW-READY, but real live order execution must remain disabled until the above missing components are implemented, tested, and operationally validated.
