# Safe Incremental Update Plan

Primary rule: preserve the existing app. Do not delete existing UI, routes, APIs, logic, docs, tests, or features unless a clear bug requires a minimal fix.

## Strategy

- Add new modules when possible.
- Keep the current dashboard and endpoints working.
- Edit existing files only for small route, card, or compatibility changes.
- Run compile/tests after each phase.
- Missing config must default to PAPER or READ_ONLY.
- Missing data must show DATA_UNAVAILABLE.
- Weak signal must show NO_TRADE.
- Any real-money uncertainty must stay BLOCKED.

## Phase 1 status

Phase 1 safe configuration foundation has been added:

- Safe config module.
- Trading mode validation defaults.
- Secret masking helpers.
- Safe public config structure.
- Updated `.env.example`.
- `README_ENV_SETUP.md`.
- Config tests.

## Phase 2 status

Phase 2 trading-mode wiring has been prepared as an opt-in local patch script because some Codespaces contain uncommitted `web_app.py` edits.

- `scripts/patch_phase2_trading_modes.py`
- `tests/test_phase2_trading_modes_contract.py`

## Phase 3 status

Phase 3 market data safety foundation has been added:

- MarketDataProvider interface.
- ExistingDataProvider adapter.
- MarketDataHealthService with CONNECTED, RECONNECTING, DISCONNECTED, STALE, DATA_UNAVAILABLE states.
- Market open/closed helper using Asia/Kolkata.
- Stale-data fail-closed helper.
- Opt-in web_app patch script for `/api/market-data/health` and dashboard card.
- Phase 3 tests.

## Phase order

1. Safe config layer — **foundation added**
2. Trading modes — **patch script added**
3. Market data safety — **foundation added**
4. Signal safety wrapper
   - Preserve existing signal logic.
   - Add standard safe signal output.
   - Add blocked_reasons and confidence grade.
5. Risk engine
   - Add central risk checks.
   - Run risk checks before paper and shadow orders first.
   - Keep real-money actions blocked by default.
6. Paper trading hardening
   - Preserve current paper trading.
   - Add order lifecycle, slippage placeholder, and audit events.
7. Shadow trading
   - Add theoretical order tracking with no real broker action.
   - Add shadow report.
8. Broker adapter safety
   - Add adapter interface.
   - Add broker health endpoint.
   - Keep broker mutation methods blocked by default.
9. Persistent kill switch
   - Add durable kill switch state when storage exists.
   - Block new orders when active.
10. Audit logs
   - Add structured events and recent logs UI/card.
11. UI additions
   - Add cards only; do not remove old design.
   - Show mode, data health, broker health, kill switch, risk block, PnL, and positions.
12. Tests
   - Existing routes still render.
   - Safe defaults.
   - Secret masking.
   - Risk blocks missing stop-loss and stale data.
   - Kill switch blocks orders.
   - Paper order works.
   - Broker mutation is blocked by default.
13. Production docs
   - Add deployment, trading modes, risk controls, and live checklist docs.
14. Final report
   - Report preserved features, changed files, added files, tests, current mode, and final verdict.

## Current recommended verdict

Current status: PAPER-FOUNDATION, still NO-GO for real-money trading.
Near-term target: PAPER-READY.
Next target: SHADOW-READY after live-data shadow reports.
