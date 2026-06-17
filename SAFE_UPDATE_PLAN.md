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

## Phase 4 status

Phase 4 signal safety foundation has been added:

- Safe signal wrapper preserving existing signal logic.
- Standard safe signal format.
- Confidence grade.
- Explicit blocked reasons.
- Stale/missing data fail-closed behavior.
- BUY/SELL checks for stop-loss, targets, risk-reward, and confidence.
- Opt-in web_app patch script for `/api/signal/safe` and dashboard card.
- Phase 4 tests.

## Phase 5 status

Phase 5 central risk engine foundation has been added:

- Central `RiskEngine` and `RiskInput` model.
- Required mode, market, instrument, data, signal, stop-loss, target, risk-reward, quantity, position, loss-limit, duplicate, cooldown, kill-switch, broker, and drift checks.
- Fail-closed risk output with `go_live_allowed=false`.
- Opt-in web_app patch script for `/api/risk/check`, dashboard card, and paper order pre-check.
- Phase 5 tests.

## Phase 6 status

Phase 6 paper trading hardening foundation has been added:

- PaperOrderManager and PaperExecutionState.
- Order lifecycle statuses: CREATED, VALIDATED, RISK_APPROVED, BLOCKED, PAPER_FILLED, CANCELLED, FAILED.
- Validated quote/LTP virtual fill behavior.
- Virtual paper position tracking and P&L.
- Brokerage/slippage placeholders.
- Paper audit log.
- Read-only paper orders/trades endpoint patch script.
- Phase 6 tests.

## Phase 7 status

Phase 7 shadow trading foundation has been added:

- ShadowTradingEngine and ShadowTradingState.
- Shadow order lifecycle statuses: SHADOW_CREATED, SHADOW_VALIDATED, SHADOW_RISK_APPROVED, SHADOW_BLOCKED, SHADOW_FILLED_THEORETICAL, SHADOW_CANCELLED, SHADOW_FAILED.
- Theoretical live-data fill behavior using validated quote/LTP only.
- Theoretical shadow position tracking and P&L.
- Shadow brokerage/slippage placeholders.
- Shadow audit log, report, drift placeholder, and accuracy placeholder.
- Opt-in web_app patch script for shadow endpoints and dashboard card.
- Phase 7 tests.

## Phase 8 status

Phase 8 broker adapter safety foundation has been added:

- BrokerAdapter protocol/interface.
- ZerodhaReadOnlyAdapter for broker read-only operations.
- BlockedBrokerMutationAdapter for fail-closed place/modify/cancel/exit methods.
- BrokerHealthService with sanitized broker health output.
- Secret masking/sanitization for broker read-only payloads.
- Opt-in web_app patch script for broker health, broker quote, broker status, broker blocked mutation endpoints, and broker safety dashboard card.
- Phase 8 tests.

## Phase 9 status

Phase 9 persistent kill switch foundation has been added:

- PersistentKillSwitch module with local JSON state.
- Storage path `.alpha_gate_state/kill_switch.json`.
- Activate, reset, status, and fail-closed corrupt/unreadable handling.
- Reset confirmation phrase `RESET_KILL_SWITCH`.
- Opt-in web_app patch script for `/api/kill-switch/status`, `/api/kill-switch/activate`, `/api/kill-switch/reset`, risk integration, paper block, shadow block, and dashboard card.
- Phase 9 tests.

## Phase order

1. Safe config layer — **foundation added**
2. Trading modes — **patch script added**
3. Market data safety — **foundation added**
4. Signal safety wrapper — **foundation added**
5. Risk engine — **foundation added**
6. Paper trading hardening — **foundation added**
7. Shadow trading — **foundation added**
8. Broker adapter safety — **foundation added**
9. Persistent kill switch — **foundation added**
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

Current status: SHADOW-READY + BROKER-SAFE + PERSISTENT-SAFETY candidate, still NO-GO for real-money trading.
Next target: Durable audit logs and operational evidence reports.
