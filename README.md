# Ultimate Institutional AI Trading Platform v9.0 Foundation

This repository now contains a governance-first Python foundation for an
institutional quantitative trading ecosystem focused on alpha generation,
capital preservation, risk management, portfolio optimization, execution
quality, compliance, and operational resilience.

The code is intentionally conservative: the final signal engine will only emit
`BUY` or `SELL` when every required research, risk, liquidity, compliance,
portfolio, execution, and AI-consensus gate has approved the opportunity. Any
missing or rejected control returns `NO TRADE` with rejection reasons.

## Implemented foundation

- **Tier catalog:** a data-driven registry for all 25 v9.0 capability tiers,
  including market data, data engineering, alpha research, ML/AI, derivatives,
  portfolio construction, risk, execution, governance, surveillance,
  observability, security, resilience, live trading reliability, and the meta
  decision engine.
- **Final Signal Engine v9.0-compatible foundation:** mandatory gate checking for the platform's
  `TRADE ONLY IF` policy, confidence calibration, score validation, and final
  `BUY / SELL / HOLD / NO TRADE` decisions.
- **Risk utilities:** historical VaR, CVaR, annualized Sharpe, and fractional
  Kelly sizing helpers for risk and capital-allocation workflows.
- **Domain contracts:** canonical instruments, OHLCV bars, and level-2 order
  book snapshots with validation and order-flow imbalance metrics.
- **Data engineering:** data contracts, metadata catalog, dataset and feature
  registries, lineage checks, quality reports, and population-stability drift
  monitoring.
- **Portfolio and execution:** volatility-targeted sizing, inverse-volatility
  allocation, rebalancing, broker-neutral order intents, execution policy
  validation, and kill-switch primitives.
- **Observability and deployment:** structured audit events, health checks,
  database/API/infrastructure documentation, Docker, CI, and monitoring
  dashboard scaffolding.
- **Research, alpha, ML/AI, regimes, derivatives, and TCA:** executable
  registries, alpha/science functions, microstructure analytics, model and
  ensemble controls, Financial LLM scoring primitives, regime intelligence,
  derivatives analytics, execution algorithms, transaction cost analysis,
  governance, drift, retraining, and Tier 25 meta-decision integration.
- **Automated tests:** coverage for approval gating, missing-score blocking,
  tier catalog readiness, and risk-metric behavior.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
pytest
```

## Example

```python
from institutional_trading_platform import ApprovalGate, FinalSignalEngine, SignalInput

engine = FinalSignalEngine(minimum_confidence=0.55, minimum_score=0.50)
gates = tuple(ApprovalGate(name, True) for name in FinalSignalEngine.REQUIRED_GATES)

signal = SignalInput(
    expected_move=0.035,
    expected_sharpe=1.7,
    expected_sortino=2.1,
    expected_drawdown=0.04,
    probability_of_profit=0.68,
    bullish_probability=0.72,
    bearish_probability=0.28,
    entry=100.0,
    stop_loss=96.0,
    targets=(104.0, 108.0, 112.0, 116.0),
    dynamic_exit=101.5,
    risk_reward=3.0,
    position_size=250.0,
    capital_allocation=0.08,
    scores={score: 0.74 for score in FinalSignalEngine.REQUIRED_SCORES},
    model_votes={"alpha": 0.76, "risk": 0.71, "macro": 0.69},
)

output = engine.evaluate(signal, gates)
print(output.decision)  # BUY
```

## ALPHA-GATE X auto-trading foundation

This repository also includes a conservative ALPHA-GATE X implementation for
Indian-market auto-trading workflows.  The implementation follows the safe
chain from signal engine to risk gate to order router and audit-friendly order
states.  It defaults to `PAPER_TRADING`; live orders are blocked unless both
`TRADING_MODE=LIVE_AUTO` and `LIVE_TRADING=true` are explicitly configured.

Implemented primitives include:

- Weighted ALPHA-GATE X signal scoring with BUY / SELL / HOLD / NO_TRADE outputs.
- Mandatory risk gate checks for daily loss, trade count, open positions, spread,
  liquidity, volatility, stale feeds, broker health, first-five-minute blocking,
  and kill switch.
- Risk-per-trade position sizing using `capital * risk_percent / abs(entry - stop_loss)`.
- Paper broker fills, duplicate order prevention, and order state-machine
  transition validation.
- `.env.example` and `OPERATIONAL_VALIDATION_PLAN.md` for staged deployment.

This foundation is intentionally broker-neutral.  Zerodha Kite Connect adapters
should be connected behind the order-router interface only after paper trading,
approval-mode validation, and compliance review are complete.

## ALPHA-GATE X Phase 2 market data spine

Phase 2 adds the deterministic market-data foundation needed before live broker
execution is considered:

- Typed tick, quote, depth, instrument, OHLCV candle, timeframe, and data-quality
  models.
- Candle building for `1m`, `5m`, `15m`, `1H`, and `Daily` bars from real ticks.
- Candle finalization rule: a candle is usable by the signal engine only after a
  later tick proves that the timeframe closed; forming candles remain
  `complete=False` and are excluded by default.
- No fake data policy: if historical data is unavailable, the loader returns
  `DATA_UNAVAILABLE` rather than generating dummy candles.
- Data-quality checks for stale data, missing/invalid candles, zero volume,
  abnormal spreads, timestamp disorder, duplicate ticks, and outlier price jumps.
- Backtest foundation that processes completed candles sequentially, prevents
  future-candle access, executes entries on the next candle open, applies
  brokerage/slippage, records trades/equity, and reports core metrics.

Known remaining items: real Zerodha WebSocket streaming, Zerodha auth/session
management, Kite historical-data loading, production paper trading from live
ticks, frontend dashboard, order status confirmation, position reconciliation,
and live stop-loss/target managers.  LIVE_AUTO order execution remains out of
scope for this phase.

## ALPHA-GATE X Phase 3 indicator intelligence layer

Phase 3 adds deterministic indicator modules that feed the ALPHA-GATE X weighted
formula without fake, random, or placeholder signals:

- **VWAP pressure:** session/rolling VWAP, distance percentage, and bullish or
  bearish pressure only from completed candles with real volume.
- **ATR:** true range, ATR, ATR percentage, ATR stop-loss distance, target ranges,
  and expected move.
- **Trend regime:** EMA20/EMA50 alignment, slope, ATR percentage, and candle
  structure to classify bullish trend, bearish trend, range, high volatility,
  danger, or unknown.  Danger forces `NO_TRADE`.
- **Liquidity sweep:** previous high/low sweep, reclaim, failed breakout, and
  failed breakdown scoring.
- **Volume confirmation:** rolling average volume, expansion ratio, directional
  confirmation, and low-volume warnings.
- **Order-book imbalance:** bid/ask quantity imbalance and spread-aware scoring;
  missing depth returns `DATA_UNAVAILABLE`.
- **Market breadth:** advancing/declining/unchanged interface and breadth score;
  missing breadth returns `DATA_UNAVAILABLE`.

The Phase 3 composer returns component scores, unavailable components,
confidence grades, ATR-derived stops/targets, expected move, and reason text for
every score.  Missing non-critical data reduces confidence; missing critical
trend/VWAP/volume inputs downgrades actionable signals to `HOLD`; failed data
quality or danger regimes force `NO_TRADE`.  The system intentionally prefers
`HOLD`/`NO_TRADE` over fabricated confidence.

Remaining production gaps: backtest validation reports, live paper-trading loop,
real Zerodha auth/WebSocket ingestion, dashboard, real broker approval mode,
position reconciliation, stop-loss/target live management, and any guarded
1-quantity live rollout.

## ALPHA-GATE X Phase 4 validation and institutional report

Phase 4 adds an honest validation layer for historical strategy assessment before
any live integration is considered:

- **Performance metrics:** total/winning/losing trades, win rate, gross/net P&L,
  profit factor, expectancy, average win/loss, average risk-reward, max drawdown,
  Sharpe, Sortino, Calmar, streaks, exposure time, no-trade percentage, holding
  period, slippage cost, and brokerage cost.
- **Equity analytics:** equity curve, drawdown curve, peak equity, per-trade P&L,
  daily P&L, and monthly P&L.
- **Walk-forward validation:** rolling train/test windows for time-series data;
  strategy evaluation runs only on out-of-sample test windows with no random
  splitting and no test-fold optimization.
- **Regime, symbol, and time analysis:** performance by trend regime, symbol,
  hour, weekday, and month, plus first-5-minute and last-15-minute diagnostics.
- **Risk report:** daily-loss, max-trade, max-position, kill-switch, stale-data,
  `DATA_UNAVAILABLE`, bad-data, and rejected-signal summaries.
- **Go-live gate:** defaults require at least 100 trades, profit factor >= 1.5,
  max drawdown <= 15%, win rate >= 50%, non-suspicious no-trade percentage, no
  critical data-quality errors, non-negative out-of-sample walk-forward P&L,
  acceptable losing streak, and positive expectancy.
- **Exports:** JSON validation report, Markdown report, trades CSV, and equity
  curve CSV.

A passing backtest is still not a profit guarantee.  It is only evidence for the
next staged controls: live paper trading, Zerodha auth/WebSocket ingestion,
dashboard review, real broker approval mode, reconciliation, and finally a
small guarded live rollout after operational validation.

## Safety model

The platform foundation defaults to capital preservation:

1. Validate normalized signal inputs before evaluation.
2. Require every final-signal gate to be present and approved.
3. Require every institutional score to be present and above threshold.
4. Calibrate confidence from directional probabilities, required scores, and
   model consensus.
5. Route blocked opportunities to `NO TRADE` with zero executable size and no
   execution prices.

This is a software foundation and not financial advice. Production deployment
must include exchange/broker integrations, independent model validation,
security controls, regulatory review, audited data lineage, and human-approved
operating procedures.


## Production documentation

- Repository audit and implementation roadmap: `docs/repository_audit.md`
- Architecture diagrams: `docs/architecture.md`
- Database schema: `docs/database_schema.sql`
- API specification: `docs/api_spec.yaml`
- Deployment guide: `docs/deployment_guide.md`
- Security review: `docs/security_review.md`
- Performance review: `docs/performance_review.md`
- Final readiness report: `docs/final_readiness_report.md`

## Deployment assets

- Container image definition: `Dockerfile`
- Compose test runner: `infrastructure/docker-compose.yml`
- CI pipeline: `.github/workflows/ci.yml`
- Monitoring dashboard scaffold: `grafana/dashboards/platform_overview.json`

## AEGIS Quant Trading Platform web app

Phase 1 (Market Data Spine) remains intact. The AEGIS web layer starts at
Phase 2 and runs sequentially through Phase 24 with conservative validation
metadata on every response:

- `data_source`
- `data_timestamp`
- `validation_status`

The app refuses to synthesize unavailable trading claims. Missing OI, PCR, IV,
market depth, order flow, alpha, confidence, expected move, or validation
evidence is reported as `DATA_UNAVAILABLE`; insufficient evidence routes the
meta decision to `NO_TRADE`.

Run the dashboard locally with the Python standard library server:

```bash
python -m institutional_trading_platform.web_app
```

Then open `http://127.0.0.1:8080/` or query:

```bash
curl http://127.0.0.1:8080/api/status
curl http://127.0.0.1:8080/api/demo
```

The `/api/demo` endpoint uses clearly labelled demo bars for UI inspection only
and must not be treated as live trading evidence.

## Phase 5: Live Paper Trading Loop

Phase 5 adds a **paper-only runtime orchestration layer** for ALPHA-GATE X. It simulates the live path without touching any real broker order API:

```text
TickReceived
→ DataQualityChecker
→ CandleBuilder finalized candles only
→ IndicatorSignalComposer
→ PaperRiskMonitor
→ PaperBroker virtual fill
→ PaperPortfolio P&L
→ Runtime audit trail
→ LivePaperRuntimeReport / Phase 4 ValidationReport conversion
```

### Runtime architecture

The runtime package contains:

- `runtime/runtime_config.py` — safe runtime configuration. `RuntimeConfig.trading_mode` defaults to `PAPER_TRADING`, and any attempt to instantiate Phase 5 with `LIVE_AUTO` raises a clear error.
- `runtime/event_bus.py` — synchronous in-memory event bus for `TickReceived`, `CandleFinalized`, `SignalGenerated`, `RiskBlocked`, `PaperOrderCreated`, `PaperOrderFilled`, `PaperPositionOpened`, `PaperPositionClosed`, `PaperPnLUpdated`, `RuntimeHeartbeat`, and `RuntimeError`.
- `runtime/live_paper_engine.py` — receives ticks, validates data quality, updates candles, runs the indicator composer only on finalized candles, applies risk checks, sends eligible BUY/SELL signals to the paper broker, and emits auditable events.
- `runtime/session_manager.py` — deterministic market-session state, square-off detection, and daily reset support with configurable timezone defaults for Indian market hours.
- `runtime/audit_store.py` — in-memory audit store with queries by `correlation_id`, symbol, and event type, plus JSON export.

### Paper broker and portfolio behavior

The `paper_trading` package implements virtual execution only:

- `PaperBroker` supports deterministic market fills, limit-order non-fill/open behavior, stop-loss triggers, target triggers, square-off, brokerage, slippage, lifecycle status, and rejected virtual orders.
- `PaperPortfolio` tracks cash, open positions, closed positions, realized P&L, unrealized P&L, total equity, exposure, daily P&L, and per-symbol P&L.
- `PaperRiskMonitor` blocks daily loss breaches, max trades, max open positions, max exposure, stale data, and kill switch conditions.

### Safety rule: no real orders in Phase 5

Phase 5 deliberately does **not** implement Zerodha live order placement, Kite order APIs, `LIVE_AUTO`, or any real-money execution. The runtime is hard-wired to paper mode, paper order IDs use a `paper-` prefix, and converted validation reports keep `go_live_allowed=false`. A Phase 5 report may recommend `READY_FOR_APPROVAL_MODE`, but it never recommends direct `LIVE_AUTO`.

### Running paper mode in code

```python
from institutional_trading_platform.runtime import LivePaperTradingEngine, RuntimeConfig
from institutional_trading_platform.market_data_spine import Tick

engine = LivePaperTradingEngine(config=RuntimeConfig(allowed_symbols=("RELIANCE",)))
engine.on_tick(Tick(...))
report = engine.build_report()
validation_report = engine.to_validation_report()
```

Interpret the runtime report conservatively:

- `CONTINUE_PAPER` means keep collecting paper evidence.
- `READY_FOR_APPROVAL_MODE` means the paper sample may be ready for manual approval-mode testing, not live auto.
- `FAIL` means runtime errors or risk/data-quality issues require fixes before continuing.

### Remaining production gaps after Phase 5

Still intentionally missing: Zerodha auth, Zerodha WebSocket ingestion, real Kite historical loader, dashboard, broker-backed approval mode, order confirmation/reconciliation, live stop-loss/target managers, and any guarded 1-quantity live rollout. Backtest and paper success do not guarantee future profit.

## Phase 6: Zerodha Live Data + Reconciliation + Approval Mode Only

Phase 6 adds broker-adjacent safety services without enabling auto-live execution. The system may ingest Zerodha-style live market-data payloads and generate approval requests, but it still does **not** place real orders automatically.

### Zerodha setup and required environment variables

Configure credentials through environment variables only; API keys/tokens are never hardcoded:

```env
ZERODHA_API_KEY=your_api_key
ZERODHA_ACCESS_TOKEN=your_access_token
ZERODHA_REDIRECT_URL=http://localhost:8000/auth/zerodha/callback
ZERODHA_INSTRUMENT_DUMP_PATH=./data/zerodha_instruments.csv
ENABLE_ZERODHA_WEBSOCKET=false
ENABLE_APPROVAL_REQUIRED=false
REAL_ORDER_PLACEMENT_ENABLED=false
```

`ZerodhaAuthService` returns `ZERODHA_UNAVAILABLE` when `ZERODHA_API_KEY` or `ZERODHA_ACCESS_TOKEN` is missing. This is a safe block state, not a fake connection.

### Live-data ingestion and instrument resolution

- `ZerodhaInstrumentManager` loads a Zerodha instrument dump, validates exchange/segment/lot size/tick size, caches instruments locally, and emits `InstrumentResolved` or `InstrumentResolutionFailed`.
- `ZerodhaWebSocketMarketDataAdapter` maps Kite-style WebSocket payloads into internal `Tick` objects while preserving exchange timestamp, local receive timestamp in the emitted event, symbol, LTP, volume, and top-of-book depth when available.
- Existing Phase 5 `DataQualityChecker` continues to block stale, malformed, duplicate, out-of-order, abnormal-spread, and outlier ticks before candle/signal processing.
- Signals are still generated only from finalized candles.

### Broker reconciliation requirement

`BrokerReconciliationService` compares broker ground truth against local approval state for positions, holdings/orders/trades context, quantity mismatch, average-price mismatch, missing orders, rejected orders, unexpected open positions, and stale broker state. It emits `BrokerReconciliationPassed` or `BrokerReconciliationFailed`. If reconciliation fails, approval requests are blocked.

### Approval mode, previews, and no-auto-trading rule

`APPROVAL_REQUIRED` mode creates `TradeApprovalRequest` records only after reconciliation has passed. User approval is required before a `ZerodhaOrderPreview` is generated. The preview includes symbol, exchange, side, quantity, order type, product, price, stop loss, target, and risk amount.

The default real-order wrapper always returns `NO_REAL_ORDER_PLACED` and emits `RealOrderBlocked`. No Kite order placement API is called in production behavior, and `RuntimeConfig` continues to reject `LIVE_AUTO`.

### SL/target monitoring design

`SLTargetMonitor` tracks approved trade plans and monitors LTP against stop-loss/target levels. It emits `ExitSuggested` and generates an exit-order preview only; it does not auto-exit. Exit execution still requires explicit approval.

### Operational notes and final safety report

- Paper mode remains the default and safest mode.
- Approval mode is broker-adjacent but not automatic trading.
- Broker reconciliation must pass before any approval request is created.
- Missing Zerodha credentials, unknown symbols, stale data, and reconciliation drift all fail safe.
- `go_live_allowed` remains `false`; Phase 6 cannot authorize `LIVE_AUTO`.

### Remaining production gaps after Phase 6

Still missing: production WebSocket connection lifecycle/reconnects, persistent PostgreSQL audit storage, frontend approval dashboard, alerting, broker-backed postback reconciliation, manual exit workflow UI, 30-day shadow-run gate, and any future small-quantity live rollout. No fake broker confirmation, no fake accuracy, and no automatic live trading are implemented.

## Phase 7: Dashboard, Alerting, and 30-Day Shadow Run Gate

Phase 7 adds a read-only operational layer on top of the Phase 5/6 audit events. It does **not** add order placement, live-auto execution, or fake dashboard data.

### Dashboard usage

`DashboardSummaryService` reads from the existing in-memory audit store and summarizes only observed events:

- runtime mode
- Zerodha auth and WebSocket status
- subscribed symbols and last tick time
- stale feed status
- finalized candle and signal counts
- approval requests, order previews, blocked real orders
- reconciliation status
- open approved plans and exit suggestions
- realized/unrealized paper P&L
- risk block reasons and kill switch status
- `go_live_allowed=false`

### Read-only API endpoints

`ReadOnlyRuntimeAPI` provides function-level equivalents for safe read-only endpoints:

```text
GET /health
GET /runtime/status
GET /runtime/events
GET /runtime/events/{correlation_id}
GET /runtime/symbols/{symbol}
GET /runtime/report
GET /approvals/pending
GET /reconciliation/status
GET /risk/status
GET /shadow-run/status
```

There is no buy/sell endpoint, no auto-trade toggle, and no endpoint that calls a broker order API.

### Alert types

`AlertManager` converts operational events into stored `AlertEmitted` events for:

- Zerodha disconnected
- auth failed
- stale feed
- malformed/unresolved tick incidents
- reconciliation failed or unexpected broker position
- risk block / kill switch active
- approval pending
- exit suggested
- paper drawdown breach
- daily loss breach

### Shadow-run gate rules

`ShadowRunValidator` tracks the 30-day paper/shadow process:

- trading days completed and market sessions observed
- total signals, approvals, previews, and blocked orders
- reconciliation failures, stale feed incidents, and data-quality failures
- max paper drawdown and daily P&L stats
- signal distribution and paper win/loss metrics
- uptime percentage and incident log

The strict gate requires 30 trading days, minimum sample count, zero real-order safety violations, zero unresolved reconciliation drift, connection stability, data-quality health, drawdown/profit-factor/win-rate thresholds, and risk-block sanity.

### Manual review requirement and final safety report

Phase 7 can return only:

```text
CONTINUE_PAPER
CONTINUE_SHADOW
READY_FOR_MANUAL_REVIEW
```

It never returns `LIVE_AUTO_READY`, and `go_live_allowed` remains `false` even when the shadow run is clean. A human manual review is required before any future broker-backed phase.

### Shadow run report example

```text
ShadowRunStatus(
  trading_days_completed=30,
  total_signals=120,
  blocked_orders_count=0,
  reconciliation_failures=0,
  uptime_percentage=98.5,
  recommendation=READY_FOR_MANUAL_REVIEW,
  go_live_allowed=False
)
```

### Remaining production gaps after Phase 7

Still missing: persistent PostgreSQL/SQLite audit storage, durable Redis-like event replay, crash recovery, production WebSocket reconnect supervision, a read-only frontend dashboard, notification channels, and later manual-review workflows. No fake live trading, fake broker confirmation, fake accuracy, `LIVE_AUTO`, real order placement, or `go_live_allowed=true` behavior is implemented.

## Phase 8: Persistence, Durable Audit Store, and Crash Recovery

Phase 8 adds durable local evidence for paper/shadow operations. It does **not** add live auto-trading, real broker order placement, or fake broker confirmations.

### SQLite persistence setup

`SQLiteAuditStore` is the default local/dev durable audit backend:

```python
from institutional_trading_platform.runtime import SQLiteAuditStore, PersistentEventBus

store = SQLiteAuditStore("./alpha_gate_x_audit.db")
bus = PersistentEventBus(store)
```

The in-memory audit store remains available for isolated tests, but shadow-run proof should use SQLite or a future durable backend.

### Audit schema

The `runtime_events` table stores every runtime event with:

```text
event_id
event_type
timestamp
correlation_id
symbol
source
severity
payload_json
created_at
```

Queries are available by event id, correlation id, symbol, event type, severity, time range, and latest N events. JSON payloads are validated before insertion. Schema initialization is safe to run repeatedly and creates a `schema_migrations` table; destructive migrations are not performed by default.

### Snapshot restore behavior

`RuntimeStateSnapshot` persists recoverable state including current mode, subscribed symbols, paper positions, approved plans, pending approvals, cash/equity, realized/unrealized P&L, kill switch status, reconciliation status, last processed candle timestamp, and last tick timestamp per symbol.

On startup, the latest snapshot can be restored from SQLite. If no valid snapshot exists, or if the snapshot indicates `SAFE_RECOVERY`, the runtime must stay blocked until manual/reconciliation checks complete.

### Crash recovery process

`CrashRecoveryService` emits:

```text
RecoveryStarted
RecoveryCompleted
RecoveryFailed
```

On restart it loads the last snapshot, unresolved approval events, open approved plans, and requires broker reconciliation before allowing new approval requests. It never assumes local state is correct without reconciliation.

Example:

```python
from institutional_trading_platform.runtime import CrashRecoveryService

recovery = CrashRecoveryService(store, event_bus=bus)
status = recovery.recover(reconciliation_passed=False)
assert status.mode == "SAFE_RECOVERY"
assert status.trading_blocked
```

### Event durability and idempotency guarantees

`PersistentEventBus` writes each event to SQLite before returning success to callers. If persistence fails, callers receive `PersistenceUnavailable`, and trading/approval decisions must be blocked. Approval requests and order previews should be created only through persistent event flows.

Processed idempotency keys are stored in `processed_idempotency_keys`. The order-preview wrapper uses deterministic keys such as `preview:{correlation_id}` to block duplicate previews after restart.

### Read-only API additions

The Phase 7 read-only API facade now includes durable methods for:

```text
latest persisted events
event lookup by event_id
snapshot status
recovery status
persistence health
```

No endpoint or facade method places orders.

### Shadow-run persistence

`ShadowRunValidator` can operate against `SQLiteAuditStore`, so trading-day progress, incident logs, signal counts, blocked orders, reconciliation failures, and P&L evidence survive restart. Shadow gates must use persisted evidence for operational proof.

### Remaining production gaps and PostgreSQL notes

SQLite is the local/dev default. A future PostgreSQL migration should keep the same audit-store interface, tables, indexes, idempotency keys, snapshots, and non-destructive migration contract. Still missing: production DB connection management, WAL shipping/backups, encrypted secrets, multi-process locking, Redis-like replay queues, and crash-tested deployment automation.

Final safety report for Phase 8:

- No fake persistence is used for durable tests.
- No fake broker confirmation is introduced.
- No fake shadow evidence is generated.
- `LIVE_AUTO` remains rejected.
- Real order placement remains blocked by default.
- `go_live_allowed=true` is not introduced.

## Phase 9: Production Hardening, Observability, and Deployment Readiness

Phase 9 hardens the paper/shadow/approval foundation for operations. It still does **not** enable `LIVE_AUTO`, real order placement, fake broker confirmations, or `go_live_allowed=true`.

### Config profiles

`ProductionRuntimeConfig` supports environment-based profiles:

```text
LOCAL
PAPER
SHADOW
APPROVAL_REQUIRED
SAFE_RECOVERY
```

Use:

```env
ALPHA_GATE_PROFILE=LOCAL
TRADING_MODE=PAPER_TRADING
AUDIT_DB_PATH=./alpha_gate_x_audit.db
LIVE_TRADING=false
```

Invalid profiles fail closed into `SAFE_RECOVERY`; `LIVE_AUTO` is rejected and converted to a non-live safe state with validation failure reasons. `SHADOW` and `APPROVAL_REQUIRED` require Zerodha credentials to be present in environment variables only.

### Health checks

`HealthCheckService` provides read-only checks for:

- liveness
- readiness
- persistence health
- Zerodha auth status
- WebSocket/feed freshness
- reconciliation freshness/failure
- recovery mode
- shadow-run gate health

Readiness fails if persistence is unavailable, config is invalid, `SAFE_RECOVERY` is active, reconciliation is failing/stale, or market feed is stale during session.

### Metrics and structured logs

`RuntimeMetrics` tracks runtime mode, tick/candle/signal counts, approvals, previews, blocked real orders, reconciliation pass/fail counts, stale feed incidents, malformed tick incidents, persistence failures, recovery status, API request count, latency buckets, shadow-run recommendation, and kill switch status.

`StructuredLogger` redacts secret-like fields before producing JSON logs.

### Docker/local run

Local/dev artifacts are included:

```bash
make test
make compile
make check
make init-db
make export-audit-json
docker compose up --build
```

The root `docker-compose.yml` uses local SQLite/dev settings and does not include secrets.

### Security controls

- Secret redaction for logs/events/errors.
- Safe error responses that avoid token/key leakage.
- External payloads are validated before conversion to internal ticks/events.
- Broker-facing order code emits blocked unsafe-action events and defaults to `NO_REAL_ORDER_PLACED`.
- Read-only APIs expose status/report data only; no order-placement method is added.

### Production hardening status

Phase 9 adds operational hardening, but it is not a claim of production/live-trading readiness. Remaining gaps include PostgreSQL implementation, hosted secrets management, production WebSocket supervision, deployment monitoring, backups, alert delivery channels, and manual compliance review.

Final production-hardening report:

- No fake production readiness is claimed.
- No fake broker confirmation is implemented.
- No fake metrics are generated.
- `LIVE_AUTO` remains rejected.
- Real order placement remains blocked.
- `go_live_allowed=true` remains unavailable.

## Phase 10: Real Shadow Trading Orchestrator and Evidence Pack

Phase 10 coordinates the already-safe Phase 5-9 pieces into a read-only shadow workflow. It still does **not** enable `LIVE_AUTO`, does not place real orders, and does not fabricate broker confirmations or shadow evidence.

### Shadow orchestrator usage

`ShadowTradingOrchestrator` verifies prerequisites before processing ticks:

1. load and validate production config
2. verify durable persistence
3. recover runtime state
4. verify Zerodha auth availability
5. require broker reconciliation pass
6. ingest live/paper ticks through the existing candle builder
7. generate signals only from finalized candles
8. create approval requests only after reconciliation passes
9. generate order previews only
10. keep SL/target handling as exit suggestions only
11. update persisted shadow-run evidence

If any prerequisite fails, the orchestrator returns `BLOCKED` or `SAFE_RECOVERY` and blocks workflow progress.

### CLI commands

Safe Phase 10 scripts are read-only with respect to broker orders:

```bash
python scripts/run_shadow_day.py
python scripts/export_evidence_pack.py
python scripts/generate_daily_report.py
python scripts/check_manual_review_gate.py
```

### Evidence pack export

`EvidencePackGenerator` exports:

- audit events JSON
- runtime snapshot JSON
- shadow run status JSON
- validation report JSON
- dashboard summary JSON
- reconciliation summary JSON
- risk summary JSON
- alerts JSON
- config profile summary with secrets redacted
- safety report JSON
- markdown executive summary

Sample metadata:

```text
{
  "pack_id": "evidence-...",
  "sections": ["audit_events_json", "runtime_snapshot_json", "shadow_run_status_json", "safety_report_json", "markdown_executive_summary"],
  "go_live_allowed": false
}
```

### Daily workflow and report

`DailyShadowReportGenerator` summarizes each trading day: observed symbols, session uptime, ticks, finalized candles, signals, approvals, previews, blocked order attempts, reconciliation failures, stale/data-quality incidents, paper P&L, drawdown, alerts, incidents, and recommendation.

Sample daily report:

```text
DailyShadowReport(
  trading_day=2026-01-01,
  symbols_observed=("RELIANCE",),
  ticks_received=12000,
  candles_finalized=75,
  signals_generated=4,
  previews_generated=0,
  blocked_order_attempts=0,
  recommendation=CONTINUE_SHADOW,
  go_live_allowed=False
)
```

### Manual review process

`ManualReviewGate` checks:

- 30 trading days complete
- sufficient samples
- no unresolved reconciliation drift
- zero unsafe real-order attempts
- acceptable data quality and feed freshness
- drawdown/profit-factor/win-rate thresholds
- operational runbook followed
- evidence pack exported
- human reviewer sign-off required

It returns only:

```text
CONTINUE_SHADOW
BLOCKED_FOR_REVIEW
READY_FOR_MANUAL_REVIEW
```

It never returns `LIVE_AUTO_READY`, and `go_live_allowed` remains `false`.

### Remaining Phase 10 limitations

Still missing: actual production WebSocket runner, external alert delivery, hosted dashboard UI, compliance review records, signed evidence-pack storage, and any future broker-supervised manual execution path. No fake live trading, fake broker confirmation, fake shadow evidence, `LIVE_AUTO`, real order placement, or `go_live_allowed=true` behavior is implemented.

## Phase 11: Strategy Robustness, Anti-Overfitting, and Market-Regime Validation

Phase 11 adds a conservative robustness layer before any manual review can progress. It still does **not** enable `LIVE_AUTO`, does not place real orders, and does not treat a good backtest or shadow run as proof of future profit.

### Robustness validation process

`StrategyRobustnessValidator` reviews generated signals and paper/backtest outcomes across:

- out-of-sample evidence
- walk-forward fold performance
- parameter sensitivity
- market-regime splits
- symbol-wise robustness
- timeframe-wise robustness
- volatility buckets
- trend/range/choppy buckets
- news-gap and low-liquidity exclusion tags

The validator returns a `RobustnessReport` with a `RobustnessScorecard`; missing OOS/walk-forward evidence is a failed check rather than an assumed pass.

### Anti-overfitting checks

The scorecard flags common false-confidence patterns:

- too few trades
- profits concentrated in one symbol
- profits concentrated in one day
- high variance expectancy
- unstable win rate or profit factor
- excessive drawdown clustering
- suspiciously smooth equity curve
- unrealistic no-trade percentage
- unrealistic fill assumptions
- look-ahead-bias suspicion
- repainting suspicion

Critical flags such as unrealistic fills, look-ahead suspicion, or repainting suspicion force strategy redesign.

### Scorecard interpretation

Allowed recommendations are only:

```text
CONTINUE_VALIDATION
REDESIGN_STRATEGY
READY_FOR_MANUAL_REVIEW
```

The scorecard includes `overall_score`, data-quality, sample-size, regime/symbol/timeframe stability, drawdown quality, execution realism, and overfitting-risk sub-scores. `go_live_allowed` remains `false` for every Phase 11 result.

Sample robustness scorecard:

```text
RobustnessScorecard(
  overall_score=82.5,
  sample_size_score=100.0,
  regime_stability_score=78.0,
  symbol_stability_score=80.0,
  execution_realism_score=100.0,
  recommendation=READY_FOR_MANUAL_REVIEW,
  go_live_allowed=False
)
```

### Evidence-pack and manual-review requirements

Evidence packs now include a `robustness_validation_json` section containing the scorecard, failed robustness checks, regime report, symbol concentration report, timeframe report, parameter sensitivity report, and overfitting warnings.

`ManualReviewGate` cannot return `READY_FOR_MANUAL_REVIEW` unless robustness score passes, no critical overfitting flags exist, OOS/walk-forward evidence exists, execution realism passes, and regime stability passes. This is still only manual-review readiness, never live-auto readiness.

### Remaining Phase 11 limitations

Robustness validation depends on real historical/live-shadow evidence being supplied by the operator. It does not fabricate OOS samples, broker confirmations, news labels, or liquidity tags. Hosted dashboards, compliance sign-off storage, and any broker-supervised real execution path remain future work.

## Phase 12: Portfolio Construction and Position Sizing

Phase 12 turns individual ALPHA-GATE X signals into a portfolio-managed paper/shadow allocation process. It still does **not** enable `LIVE_AUTO`, does not place orders, and does not treat portfolio approval as permission to trade real capital.

### Portfolio construction process

`PortfolioConstructionEngine` accepts candidate signal allocations and applies portfolio-level controls before any approval workflow can use the proposed quantities:

- volatility-targeted allocation
- capped fractional Kelly sizing
- symbol concentration limits
- sector exposure limits
- gross exposure limits
- pairwise correlation limits
- current-position concentration checks
- portfolio VaR/CVaR controls
- portfolio drawdown controls
- risk-per-trade quantity clipping

The result is a `PortfolioConstructionResult` containing approved paper/shadow allocations, target weights, rejected symbols with exact reasons, and a `PortfolioRiskReport`.

### Position sizing and risk controls

Phase 12 sizing is intentionally conservative. A candidate can pass the signal engine but still be clipped or rejected if it breaches symbol, sector, correlation, VaR, CVaR, drawdown, or execution-risk constraints. Kelly sizing is capped, and zero/negative-edge candidates receive zero Kelly allocation.

### Sample portfolio risk report

```text
PortfolioRiskReport(
  gross_exposure=0.62,
  portfolio_var_pct=1.4,
  portfolio_cvar_pct=2.1,
  drawdown_pct=3.0,
  approved=True,
  go_live_allowed=False
)
```

### Remaining Phase 12 limitations

The portfolio layer relies on supplied volatility, return, sector, and correlation inputs. It does not fabricate factor covariance, sector mapping, liquidity capacity, or execution fills. Portfolio approval remains paper/shadow evidence only; real orders and `LIVE_AUTO` remain blocked.

## Phase 13: Multi-Strategy Orchestration and Capital Allocation

Phase 13 upgrades ALPHA-GATE X from a single-strategy signal engine into a read-only multi-strategy portfolio manager. It still does **not** enable `LIVE_AUTO`, does not place real orders, and does not fabricate alpha, diversification, robustness, or performance.

### Strategy registry and discovery

`StrategyRegistry` stores strategy metadata including strategy id/name/version, supported symbols/timeframes/regimes, risk profile, expected holding period, and enabled flag. Default contracts include `ALPHA_GATE_X`, `MOMENTUM`, `MEAN_REVERSION`, `BREAKOUT`, `VOLATILITY_EXPANSION`, and `MARKET_BREADTH` as metadata-driven interfaces.

### Health scoring and regime selection

`StrategyPerformanceTracker` computes current and rolling 20/50/100-trade metrics for each strategy. `StrategyHealthScorer` combines performance, robustness, stability, drawdown, and execution scores into `HEALTHY`, `WATCHLIST`, `DEGRADED`, or `DISABLED`. Regime compatibility scores map strategies to `TRENDING`, `RANGING`, `CHOPPY`, `HIGH_VOLATILITY`, and `LOW_VOLATILITY` conditions.

### Capital allocation and correlation controls

`CapitalAllocationEngine` supports equal, performance-weighted, robustness-weighted, volatility-adjusted, and blended capital allocation. Disabled strategies receive zero allocation, and allocation caps can leave capital unallocated rather than forcing unsafe concentration. `StrategyCorrelationAnalyzer` reports P&L correlation, signal correlation, trade overlap, excessive similarity, duplicate alpha, and concentrated-alpha warnings.

### Unified signal aggregation and conflict resolution

`UnifiedSignalAggregator` combines strategy signals using allocation, confidence, health, and robustness weighting. Opposing BUY/SELL votes produce a `ConflictResolutionReport` with conflict score and confidence reduction before emitting a unified BUY/SELL/HOLD/NO_TRADE shadow decision.

### Evidence pack and manual-review gate

Evidence packs now include `multi_strategy_json` with registered strategies, health scores, allocations, correlation matrix, overlap warnings, regime compatibility, unified decisions, and conflict reports. `ManualReviewGate` now requires acceptable strategy diversification, correlation profile, health scores, robustness scores, and no disabled strategy dominating allocation before returning `READY_FOR_MANUAL_REVIEW`; `go_live_allowed` remains `false`.

### Remaining Phase 13 limitations

The orchestration layer requires real strategy performance and signal histories from shadow/backtest runs. Placeholder strategy metadata is not fake alpha and does not imply profitability. Hosted strategy dashboards, online allocator tuning, and any broker-supervised real execution path remain future work.

## Phase 14: Options/F&O Risk Engine and Greeks Control

Phase 14 adds a derivatives risk layer for paper/shadow validation. It does **not** enable `LIVE_AUTO`, does not place F&O orders, and does not fabricate option-chain, IV, or Greeks data.

### Option contracts and chain analytics

`FNOOptionContract` captures option symbol, strike, expiry, call/put, lot size, underlying, instrument token, exchange, and option type. `analyze_option_chain` identifies ATM strikes, ITM/OTM classification, strike distance, open interest, change in OI, volume, IV, and PCR. Missing option-chain fields return `DATA_UNAVAILABLE`.

### Greeks and portfolio exposure

`compute_position_greeks` and `aggregate_portfolio_greeks` compute/store Delta, Gamma, Theta, Vega, and Rho per position and portfolio. If spot, IV, or expiry inputs are unavailable, portfolio Greeks return `DATA_UNAVAILABLE` instead of guessed values.

Sample Greeks report:

```text
PortfolioGreeksReport(
  net_delta=420.5,
  net_gamma=18.2,
  net_theta=-950.0,
  net_vega=710.4,
  net_rho=85.0,
  data_status=OK,
  go_live_allowed=False
)
```

### F&O risk controls

`assess_fo_risk` checks max Delta/Gamma/Theta/Vega/Rho, expiry concentration, underlying concentration, and lot exposure. `analyze_implied_volatility` returns IV percentile, IV rank, and LOW/NORMAL/HIGH IV regime. `analyze_expiry_risk` flags near-expiry and concentrated expiry stress, while `analyze_gap_risk` flags overnight/event/earnings gap warnings.

Sample options risk report:

```text
FORiskReport(
  approved=False,
  warnings=("max delta limit breached", "max lot exposure breached"),
  go_live_allowed=False
)
```

### Evidence and manual-review requirements

Evidence packs now include `options_risk_json` with Greeks, IV metrics, expiry metrics, concentration metrics, gap risk, and risk warnings. `ManualReviewGate` requires acceptable Greeks, concentration, expiry risk, and IV exposure before `READY_FOR_MANUAL_REVIEW`; this remains manual-review evidence only and `go_live_allowed` remains `false`.

### Remaining Phase 14 limitations

The derivatives layer depends on real option-chain, IV, spot, expiry, OI, and event-risk inputs supplied by data providers. It does not create fake Greeks, fake IV, fake broker confirmation, or any real F&O execution path.

## Phase 15: Execution Realism, Slippage, Latency, and Microstructure Simulation

Phase 15 makes paper/shadow execution intentionally more conservative so results do not depend on idealized fills. It still does **not** enable `LIVE_AUTO`, does not place broker orders, and does not fabricate depth, liquidity, or fills.

### Execution modes

`ExecutionSimulator` supports:

- `IDEALIZED` for explicit comparison only
- `CONSERVATIVE` as the default paper execution assumption
- `MICROSTRUCTURE_AWARE` for depth-based fills when real order-book depth is available

`PaperBroker` defaults to `CONSERVATIVE` mode. Microstructure-aware simulation requires real depth; absent depth returns `DATA_UNAVAILABLE` rather than a fake book.

### Slippage, impact, and latency assumptions

The simulator models fixed-bps, volatility-adjusted, spread-based, liquidity-adjusted, and impact-based slippage. It also estimates market impact from quantity, average traded volume, visible depth, spread, volatility, and participation rate. `LatencyModel` combines signal-generation, order-preparation, user-approval, broker round-trip, WebSocket delay, and candle-finalization delay into latency buckets and warnings.

### Depth-based fills and quality report

Order-book simulation supports best bid/ask, top-5 depth consumption, partial fills across multiple levels, missed limit fills, tick-size rounding, brokerage, STT/transaction charges, spread cost, slippage cost, impact cost, total execution cost, and fill realism scoring.

Sample execution quality report:

```text
ExecutionQualityReport(
  requested_quantity=100,
  filled_quantity=80,
  fill_ratio=0.80,
  realized_simulated_price=100.15,
  slippage_cost=42.0,
  impact_cost=18.0,
  latency=LatencyReport(total_decision_to_fill_ms=450, latency_bucket=NORMAL),
  warnings=("partial fill",),
  execution_quality_score=76.5,
  go_live_allowed=False
)
```

### Evidence and manual-review requirements

Evidence packs now include `execution_realism_json` with execution reports, latency reports, slippage assumptions, impact warnings, fill realism score, and fill ratio. `ManualReviewGate` requires execution evidence, acceptable fill ratio, acceptable slippage, acceptable market impact, acceptable latency, and no impossible-fill warnings before `READY_FOR_MANUAL_REVIEW`.

### Remaining Phase 15 limitations

Execution simulation depends on real depth/liquidity/volatility inputs. It does not fabricate order-book depth, real queue position, exchange matching, or broker confirmation. It remains a shadow validation tool only.


## Phase 16 — Offline Research & ML Sandbox

Phase 16 adds an **offline-only** research sandbox. It can build datasets from persisted audit/shadow/paper evidence, register features with lineage, track experiment metadata, compare baselines, and produce advisory model-risk reports. It does **not** deploy models, override rule-based ALPHA-GATE X signals, place orders, or mark `go_live_allowed=true`.

### Offline research workflow

1. Export durable audit/shadow/paper evidence from the runtime store.
2. Build a `ResearchDataset` with candles, signals, outcomes, fills, execution-quality, regime labels, portfolio state, and options-risk fields where available. Missing fields are explicitly marked `DATA_UNAVAILABLE`.
3. Register offline features in `OfflineFeatureStore` with `feature_name`, `feature_version`, `source`, timestamp, symbol/timeframe, availability status, and lineage.
4. Record `ResearchExperimentRecord` metadata for train/validation/test periods and metrics.
5. Run `MLValidationGate` to enforce chronological splits, leakage checks, minimum sample size, OOS metrics, walk-forward metrics, feature-importance sanity, regime stability, and calibration evidence.
6. Generate a `ResearchMLReport` and add it to the evidence pack as `research_ml_json`.

### Advisory-only ML policy

ML evidence can recommend only `COLLECT_MORE_DATA`, `REJECT_MODEL`, `CONTINUE_RESEARCH`, or `READY_FOR_MANUAL_RESEARCH_REVIEW`. There is no `ML_LIVE_READY` state. The helper `advisory_ml_decision()` always returns the original rule-based decision, so research output cannot override `BUY`, `SELL`, `HOLD`, or `NO_TRADE`.

### Sample research report

```json
{
  "dataset_summary": {"row_count": 250, "data_status": "OK"},
  "feature_availability": {"total_features": 12, "unavailable_features": 1},
  "validation_gate_results": {"passed": false, "failure_reasons": ["walk_forward_metrics_required"]},
  "model_risk_report": {"warnings": ["missing walk-forward metrics"]},
  "recommendation": "CONTINUE_RESEARCH",
  "ml_override_allowed": false,
  "go_live_allowed": false
}
```

### Research API facades

The read-only runtime facade exposes advisory endpoints for `/research/datasets`, `/research/features`, `/research/experiments`, and `/research/reports`. There is intentionally no model deployment endpoint and no trading endpoint in the research layer.

### Limitations

Phase 16 does not claim predictive edge or accuracy. Missing research evidence is exported as `DATA_UNAVAILABLE`; it is not treated as a pass. Manual review does not require ML success unless a future operator explicitly enables a separate research gate.

## Phase 17 — Enterprise Monitoring, Metrics, Incident Management

Phase 17 adds an enterprise monitoring layer for shadow, paper, and approval workflows only. It does not enable `LIVE_AUTO`, does not place real orders, and keeps `go_live_allowed=false`.

### Metrics registry

`MetricsRegistry` records runtime uptime, Zerodha auth status, WebSocket freshness, tick/candle/signal/approval/preview rates, blocked real-order attempts, reconciliation pass/fail rates, stale/malformed feed incidents, persistence failures, recovery events, API latency, shadow-run progress, strategy health, portfolio exposure, options Greeks exposure, execution quality, and ML research advisory status.

Metrics can be exported without external dependencies:

```text
# TYPE tick_ingestion_rate gauge
tick_ingestion_rate{symbol="RELIANCE"} 12.5
# TYPE execution_quality_score gauge
execution_quality_score 95.0
```

JSON export includes the latest sample per metric and always reports `go_live_allowed=false`.

### Incident workflow

`IncidentManager` tracks incidents such as stale feed, Zerodha auth failure, WebSocket disconnect, reconciliation drift, persistence failure, SAFE_RECOVERY, kill switch active, excessive slippage, poor fill ratio, drawdown breach, options Greeks breach, strategy degradation, and suspicious ML result. Incidents include severity (`INFO`, `WARNING`, `CRITICAL`), status (`OPEN`, `ACKNOWLEDGED`, `RESOLVED`), affected symbols, correlation ID, runbook section, and recommended action.

Sample incident report:

```json
{
  "incident_type": "persistence_failure",
  "severity": "CRITICAL",
  "status": "OPEN",
  "runbook_section": "Phase 17 incident response",
  "recommended_action": "Follow runbook and block new approvals if critical.",
  "go_live_allowed": false
}
```

### SLO tracking and alert routing

`SLOTracker` evaluates uptime, feed freshness, persistence availability, reconciliation freshness, API latency, and recovery time objective. `AlertRouter` supports console/log routing and audit-store routing. Webhook routing is a disabled placeholder unless explicitly configured; no external notification is faked.

### Manual-review monitoring requirements

Evidence packs include `monitoring_json` with metrics snapshot, incidents, alerts, SLO status, unresolved critical incidents, alert-routing status, and monitoring readiness. Manual review requires no unresolved critical incidents, acceptable SLO targets, monitoring evidence, and at least audit/log alert routing. These checks remain advisory for readiness only and never authorize live auto-trading.

### Limitations

Monitoring is based on observed runtime/audit evidence only. It does not fabricate uptime, feed freshness, external alert delivery, broker health, or operational readiness.

## Phase 18 — Governance, Compliance, Immutable Audit & Control Framework

Phase 18 adds governance controls for shadow, paper, and approval workflows. The audit chain is **tamper-evident, not tamper-proof**: every governance event stores the previous hash, event hash, chain index, and verification status so modified or missing events can be detected during review. It does not enable `LIVE_AUTO`, does not place real orders, and keeps `go_live_allowed=false`.

### Governance model

`GovernanceEvent` records config changes, strategy enable/disable actions, risk-limit changes, manual-review activity, evidence-pack exports, incident acknowledgement/resolution, unsafe action blocks, approval decisions, and policy violations. Each event includes actor, actor role, affected resource, reason, correlation ID, previous/new values, approval status, severity, and payload JSON.

### Roles and permissions

The role model includes `VIEWER`, `OPERATOR`, `RISK_MANAGER`, `REVIEWER`, and `ADMIN`. Permissions cover report viewing, incident acknowledgement/resolution, config approval, manual-review approval, evidence export, strategy disablement, and risk-limit changes. No role has permission to enable `LIVE_AUTO`.

### Four-eyes and policy engine

`FourEyesControl` requires two distinct actors for risk-limit changes, strategy enable/disable approvals, manual-review completion, and readiness sign-off. `PolicyEngine` enforces hard policies including `LIVE_AUTO_FORBIDDEN`, `REAL_ORDER_FORBIDDEN_BY_DEFAULT`, `GO_LIVE_FALSE_REQUIRED`, evidence requirements, reconciliation requirements, monitoring requirements, execution-realism requirements, robustness requirements, and options-risk requirements when F&O is enabled.

### Compliance checklist

`ComplianceChecklistReport` checks audit-chain verification, evidence export, risk-limit review, manual-review completion, incident resolution, monitoring SLOs, reconciliation cleanliness, robustness evidence, execution-realism evidence, options-risk evidence when needed, absence of unsafe broker actions, and absence of LIVE_AUTO. Recommendations are limited to `CONTINUE_SHADOW`, `BLOCKED_FOR_COMPLIANCE_REVIEW`, and `READY_FOR_MANUAL_REVIEW`.

Sample compliance report:

```json
{
  "audit_chain_verified": true,
  "evidence_pack_exported": true,
  "risk_limits_reviewed": true,
  "manual_review_completed": true,
  "no_live_auto": true,
  "recommendation": "READY_FOR_MANUAL_REVIEW",
  "go_live_allowed": false
}
```

Sample audit-chain verification:

```json
{
  "chain_valid": true,
  "checked_events": 3,
  "failures": [],
  "go_live_allowed": false
}
```

### Evidence and manual-review requirements

Evidence packs now include `governance_compliance_json` with governance events, audit-chain verification, role/permission summary, policy violations, compliance checklist, four-eyes approvals, and unresolved governance blocks. Manual review requires a valid audit chain, no unresolved critical policy violation, four-eyes sign-off where required, evidence export, and a passing compliance checklist.

### Limitations

This phase provides internal control evidence only. It is not legal advice, not regulatory certification, and not a tamper-proof ledger. Operators must still perform broker, exchange, legal, and compliance review before any future production workflow.

## Phase 19 — High Availability, Backup, Restore & Disaster Recovery

Phase 19 adds operational resilience controls for shadow, paper, and approval workflows. It does **not** enable `LIVE_AUTO`, does not place real orders, and keeps every HA/DR report at `go_live_allowed=false`.

### Backup workflow

`BackupManager` creates real local filesystem backups for audit databases, snapshots, evidence packs, governance records, and JSON exports. Each `BackupMetadata` record includes backup ID, type, timestamp, path, size, checksum, status, source path, warnings, and `go_live_allowed=false`.

Sample backup report:

```json
{
  "backup_id": "backup-...",
  "backup_type": "FULL",
  "status": "SUCCESS",
  "size": 1024,
  "checksum": "sha256...",
  "go_live_allowed": false
}
```

### Checksum and corruption detection

Backups use SHA-256 checksums. `BackupVerificationReport` returns `verified=false` with `corrupted_files` or `missing_files` when the backup payload is changed or missing. This is a corruption-detection control, not a claim that storage is immutable.

### Restore workflow

`RestoreManager` restores verified audit databases, runtime snapshots, governance records, and evidence packs into operator-selected paths. Restore is reported by `RestoreReport`; failed checksum verification or missing source files produces explicit errors instead of fake success.

Sample restore report:

```json
{
  "restore_success": true,
  "restored_objects": ["/restore/audit.db"],
  "warnings": [],
  "errors": [],
  "go_live_allowed": false
}
```

### Disaster recovery process

`DisasterRecoverySimulator` models process crash, database loss, snapshot corruption, persistence failure, restart recovery, missing backup, and stale backup scenarios. Simulations produce `DisasterRecoveryReport` with warnings/errors and never mark a workflow live-ready.

Sample DR simulation report:

```json
{
  "scenario": "RESTART_RECOVERY",
  "recovery_success": true,
  "recovery_required": false,
  "warnings": [],
  "errors": [],
  "go_live_allowed": false
}
```

### Recovery readiness and retention policy

`RecoveryReadinessValidator` requires a successful backup, recent backup timestamp, valid checksum, tested restore, tested recovery path, and valid governance/audit chain. Retention checks cover daily, weekly, and monthly backup windows and warn when the latest backup is stale or the retention window is violated.

### Business continuity checklist

`BusinessContinuityReport` combines backup verification, restore testing, recovery readiness, retention compliance, and DR simulation history. Allowed recommendations are only `CONTINUE_SHADOW`, `RECOVERY_IMPROVEMENT_REQUIRED`, and `READY_FOR_MANUAL_REVIEW`.

Sample business continuity report:

```json
{
  "backup_status": "VERIFIED",
  "restore_status": "TESTED",
  "recovery_readiness": "READY",
  "retention_compliance": true,
  "disaster_recovery_score": 100.0,
  "recommendation": "READY_FOR_MANUAL_REVIEW",
  "go_live_allowed": false
}
```

### Evidence and manual-review requirements

Evidence packs include `ha_disaster_recovery_json` with HA status, backup reports, restore reports, recovery readiness, retention compliance, DR simulations, and business continuity reports. Missing HA/DR evidence is marked `DATA_UNAVAILABLE` and is not treated as a pass. Manual review requires verified backup, tested restore, valid audit chain, `READY` recovery readiness, retention compliance, and no unresolved DR failure.

### Read-only HA API facades

The read-only runtime API exposes HA status, backups, restore status, recovery status, and business continuity status. No HA API method places orders.

### Limitations

Phase 19 does not claim full production HA, cross-region failover, broker-side recovery, or regulatory disaster-recovery certification. Operators must still run real backup drills, off-host storage validation, and business-continuity reviews before production use.

## Phase 20 — Final Certification, Human Trading Desk Workflow & Operational Readiness

Phase 20 adds the final manual-certification layer. It certifies process maturity and evidence quality for human review only. It does **not** authorize autonomous live trading, does not enable `LIVE_AUTO`, does not place real orders, and keeps `go_live_allowed=false`.

### Certification workflow

`FinalCertificationFramework` reviews certification areas: market data, signal generation, forecasting, validation, paper trading, shadow trading, reconciliation, portfolio construction, multi-strategy orchestration, options risk, execution realism, monitoring, governance, compliance, HA/DR, and evidence quality. Each `CertificationAreaReport` returns only `PASS`, `PASS_WITH_WARNINGS`, `FAIL`, or `DATA_UNAVAILABLE`.

Sample certification scorecard:

```json
{
  "passed_sections": ["Market Data", "Signal Generation", "HA/DR"],
  "warning_sections": [],
  "failed_sections": [],
  "unavailable_sections": [],
  "total_sections": 16,
  "completion_percentage": 100.0,
  "recommendation": "READY_FOR_MANUAL_CERTIFICATION",
  "go_live_allowed": false
}
```

### Review board workflow

`TradingDeskWorkflow` and `ReviewBoard` track analyst review, risk review, operations review, compliance review, and final reviewer sign-off. Review stages are limited to `PENDING`, `APPROVED`, and `REJECTED`; rejected reviews must carry a rejection reason. Review approval is a manual-certification signal only and is not a trading authorization.

### Evidence quality requirements

`EvidenceQualityValidator` checks evidence completeness, missing reports, stale reports, missing shadow data, missing robustness data, missing monitoring data, and missing compliance data. Missing certification evidence is marked `DATA_UNAVAILABLE` and is not treated as a pass.

### Final readiness interpretation

`FinalReadinessReport` combines certification, compliance, monitoring, robustness, execution realism, governance, HA/DR, and shadow-run status. Allowed recommendations are only `CONTINUE_SHADOW`, `BLOCKED_FOR_REVIEW`, and `READY_FOR_MANUAL_CERTIFICATION`.

Sample readiness report:

```json
{
  "compliance_status": "PASS",
  "monitoring_status": "PASS",
  "governance_status": "PASS",
  "ha_dr_status": "PASS",
  "critical_blockers": [],
  "recommendation": "READY_FOR_MANUAL_CERTIFICATION",
  "go_live_allowed": false
}
```

### Manual certification package

`ManualCertificationPackage` exports JSON metadata and a Markdown report containing executive summary, certification scorecard, readiness report, evidence summary, compliance summary, governance summary, risk summary, and unresolved items.

Sample package metadata:

```json
{
  "package_id": "cert-...",
  "recommendation": "READY_FOR_MANUAL_CERTIFICATION",
  "go_live_allowed": false
}
```

### Final operational checklist

The final checklist requires shadow run completion, clean reconciliation, no critical incidents, governance pass, compliance pass, valid audit chain, verified backup, tested restore, robustness pass, execution-realism pass, monitoring pass, and complete evidence. Checklist output can only be `READY_FOR_MANUAL_CERTIFICATION` or `BLOCKED`.

### Limitations

Phase 20 is not a legal, regulatory, broker, exchange, or production certification. It does not generate `LIVE_READY`, `AUTO_APPROVED`, or `GO_LIVE_ALLOWED_TRUE`. The recommendation ceiling remains `READY_FOR_MANUAL_CERTIFICATION`.
