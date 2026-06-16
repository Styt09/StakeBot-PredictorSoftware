# ALPHA-GATE X Operational Runbook

## Startup
1. Set `ALPHA_GATE_PROFILE` to `LOCAL`, `PAPER`, `SHADOW`, `APPROVAL_REQUIRED`, or `SAFE_RECOVERY`.
2. Keep `TRADING_MODE=PAPER_TRADING` unless using preview-only `APPROVAL_REQUIRED`.
3. Run `make init-db` to initialize SQLite audit persistence.
4. Run health/readiness checks before any paper or approval workflow.

## Shutdown
1. Stop tick ingestion.
2. Persist a final runtime snapshot.
3. Export audit JSON with `make export-audit-json`.
4. Confirm no pending approvals are unresolved.

## Zerodha token refresh process
Refresh tokens outside the repository, store them only in environment variables, and never commit secrets. If auth fails, remain in paper/shadow or SAFE_RECOVERY.

## Shadow-run daily checklist
- Confirm WebSocket freshness.
- Review stale/malformed tick incidents.
- Review reconciliation pass/fail state.
- Export audit evidence.
- Record daily paper P&L and drawdown.

## Reconciliation checklist
- Compare broker positions, holdings, orders, and trades.
- Resolve quantity or average-price drift.
- Investigate unexpected open positions.
- Do not create approval requests until reconciliation passes.

## Incident handling
- Auth failure: refresh Zerodha token and keep trading blocked.
- Stale feed: stop signal generation until fresh ticks return.
- Persistence failure: enter SAFE_RECOVERY and export diagnostics.
- Unexpected broker position: block approvals and reconcile manually.

## SAFE_RECOVERY procedure
1. Restore latest snapshot.
2. Load unresolved approvals and approved plans.
3. Run broker reconciliation.
4. Keep new approvals blocked until recovery completes cleanly.

## Persistence backup/export
SQLite is local/dev default. Back up the DB file and export audit JSON after every shadow session.

## Manual review process
Only `READY_FOR_MANUAL_REVIEW` may be returned after a clean 30-day shadow run. This is not live-auto approval.

## Strict no-auto-trading policy
No component may place a real order automatically. All broker-facing code must default to `NO_REAL_ORDER_PLACED` and emit a blocked unsafe-action audit event.

## Phase 10 shadow orchestrator daily workflow
1. Run `python scripts/run_shadow_day.py` before market open to confirm config, persistence, recovery, and dashboard state.
2. Confirm Zerodha auth is available and instruments resolve; if not, remain blocked.
3. Run broker reconciliation before any approval request.
4. During the session, allow only shadow tick ingestion, finalized-candle signal generation, approval requests, and order previews.
5. Do not place real orders. Exit handling remains `ExitSuggested` only.

## Phase 10 evidence pack export
After each session run:

```bash
python scripts/generate_daily_report.py
python scripts/export_evidence_pack.py > evidence-pack.json
python scripts/check_manual_review_gate.py
```

Verify the evidence pack includes audit events, snapshot, shadow status, validation/dashboard/reconciliation/risk/alert summaries, redacted config, safety report, and markdown executive summary.

## Manual review process
The manual review gate may return `READY_FOR_MANUAL_REVIEW` only after 30 trading days, sufficient samples, no unresolved reconciliation drift, zero unsafe real-order attempts, acceptable feed/data quality, drawdown/profit-factor/win-rate thresholds, runbook completion, evidence export, and human sign-off.

## Phase 10 safety limitations
`READY_FOR_MANUAL_REVIEW` is not permission for `LIVE_AUTO`. The system still has no automatic real-order path, no fake broker confirmations, and no `go_live_allowed=true` output.

## Phase 11 robustness validation checklist
1. Export the latest backtest/shadow trades and equity curve.
2. Verify out-of-sample and walk-forward evidence exists before running manual review.
3. Run robustness validation across symbols, timeframes, regimes, volatility buckets, and parameter variants.
4. Inspect failed robustness checks and overfitting warnings; do not override critical flags.
5. Confirm news-gap and low-liquidity exclusion tags are real operator evidence, not synthetic labels.
6. Export a new evidence pack with `robustness_validation_json` before manual review.

## Phase 11 manual-review hard stop
Manual review must remain blocked unless the robustness score is above threshold, sample size is sufficient, OOS/walk-forward evidence exists, execution realism passes, regime stability passes, and no critical overfitting flags exist. `READY_FOR_MANUAL_REVIEW` is still not permission for `LIVE_AUTO`, and `go_live_allowed` must remain `false`.

## Phase 12 portfolio construction checklist
1. Verify candidate signals include entry, stop, confidence, expected return, volatility, sector, win probability, and reward/risk estimates.
2. Validate supplied sector, volatility, return, and correlation data before portfolio construction.
3. Run `PortfolioConstructionEngine` before any approval request is reviewed.
4. Investigate every rejected symbol and concentration/correlation warning.
5. Confirm VaR, CVaR, drawdown, gross exposure, sector exposure, and symbol exposure are inside configured limits.
6. Treat portfolio approval as paper/shadow readiness only; it is not live-trading authorization.

## Phase 12 safety limitation
Portfolio construction can reduce and reject allocations, but it cannot prove future profit and never enables `LIVE_AUTO`, real order placement, or `go_live_allowed=true`.

## Phase 13 multi-strategy orchestration checklist
1. Register only strategies with reviewed metadata, supported regimes, expected holding period, and explicit enabled flag.
2. Refresh rolling 20/50/100-trade strategy metrics before allocation review.
3. Disable or set zero allocation for degraded strategies before manual review.
4. Check regime compatibility before accepting a strategy's signal in the unified decision.
5. Review strategy allocations, correlation matrix, trade overlap, and duplicate-alpha warnings.
6. Review every conflict report where BUY and SELL strategies oppose each other.
7. Export evidence with `multi_strategy_json` before manual review.

## Phase 13 safety limitation
Multi-strategy allocation is a shadow/manual-review control only. It cannot prove diversification or future profit, and it never enables `LIVE_AUTO`, real order placement, or `go_live_allowed=true`.

## Phase 14 options/F&O risk checklist
1. Verify option chain data includes real strike, expiry, OI, change in OI, volume, IV, lot size, and instrument token.
2. Confirm missing option-chain fields are marked `DATA_UNAVAILABLE` and are not manually filled with dummy values.
3. Review per-position and portfolio Greeks before approval review.
4. Check max Delta, Gamma, Theta, Vega, Rho, expiry concentration, underlying concentration, and lot exposure limits.
5. Review IV percentile/rank/regime, near-expiry warnings, expiry stress, overnight gap, event gap, and earnings flags.
6. Export evidence with `options_risk_json` before manual review.

## Phase 14 safety limitation
Options/F&O risk approval is shadow/manual-review evidence only. It cannot prove future option P&L and never enables `LIVE_AUTO`, real F&O order placement, or `go_live_allowed=true`.

## Phase 15 execution realism checklist
1. Confirm paper broker execution mode is `CONSERVATIVE` unless explicitly comparing against `IDEALIZED`.
2. Use `MICROSTRUCTURE_AWARE` only when real order-book depth is available; otherwise require `DATA_UNAVAILABLE`.
3. Review market, limit, partial, delayed, rejected, and missed-fill assumptions before accepting paper results.
4. Check fixed/volatility/spread/liquidity/impact slippage assumptions and fee/STT/transaction charge settings.
5. Review decision-to-fill latency buckets and warnings.
6. Review fill ratio, spread cost, slippage cost, impact cost, total execution cost, and execution quality score.
7. Export evidence with `execution_realism_json` before manual review.

## Phase 15 safety limitation
Execution simulation is not broker confirmation. It cannot prove real fills and never enables `LIVE_AUTO`, real order placement, fake depth, fake liquidity, or `go_live_allowed=true`.


## Phase 16 — Offline Research & ML Sandbox Runbook

1. Keep the runtime in PAPER/SHADOW/APPROVAL_REQUIRED only; never enable `LIVE_AUTO` for research.
2. Export persisted audit, shadow, paper-fill, execution-quality, strategy, portfolio, and options-risk evidence.
3. Build the research dataset and verify every missing field is marked `DATA_UNAVAILABLE` rather than filled with synthetic values.
4. Register each feature in the offline feature store with version, source, timestamp, symbol, timeframe, availability status, and lineage.
5. Record experiment metadata with chronological train, validation, and test periods.
6. Run leakage checks for future/target/label-like columns and confirm no look-ahead features are present.
7. Compare against majority-class, deterministic random-baseline, and rule-based baseline results.
8. Generate the model risk report and reject suspiciously high metrics, insufficient samples, regime instability, or target leakage.
9. Export `research_ml_json` into the evidence pack. Missing ML evidence must remain `DATA_UNAVAILABLE`.
10. Treat ML as advisory only: it must not override rule-based trading decisions, must not create a deployment artifact, and must not place or prepare real orders.

Allowed research recommendations are only `COLLECT_MORE_DATA`, `REJECT_MODEL`, `CONTINUE_RESEARCH`, and `READY_FOR_MANUAL_RESEARCH_REVIEW`. `go_live_allowed` must stay false.

## Phase 17 — Enterprise Monitoring & Incident Runbook

1. Start monitoring before the shadow/paper session and confirm metrics export is available in JSON and Prometheus-style text.
2. Verify metric coverage for runtime uptime, feed freshness, tick/candle/signal rates, approvals, previews, blocked real-order attempts, reconciliation status, persistence, recovery, strategy health, portfolio exposure, options Greeks, execution quality, and ML advisory status.
3. Route alerts at least to console/log or audit store. Keep webhook routing disabled unless explicitly configured and tested; do not claim external alert delivery by default.
4. Create incidents for stale feed, auth failure, WebSocket disconnect, reconciliation drift, persistence failure, SAFE_RECOVERY, kill switch active, excessive slippage, poor fill ratio, drawdown breach, Greeks breach, strategy degradation, or suspicious ML results.
5. Acknowledge incidents only after an operator has started investigation. Resolve incidents only after evidence confirms recovery.
6. Review SLO status for uptime, feed freshness, persistence availability, reconciliation freshness, API latency, and recovery time objective.
7. Export `monitoring_json` into the evidence pack before manual review.
8. Manual review is blocked while any critical incident is unresolved, SLO targets are failing, monitoring evidence is missing, or alert routing is not configured to audit/log.
9. Monitoring must not enable `LIVE_AUTO`, place orders, fake uptime, or fake external notifications. `go_live_allowed` remains false.

## Phase 18 — Governance & Compliance Runbook

1. Record governance events for every config request/approval/rejection, strategy enable/disable action, risk-limit change, manual-review start/completion, evidence export, incident acknowledgement/resolution, unsafe action block, and approval decision.
2. Verify the tamper-evident audit chain before review. Treat hash mismatch, index mismatch, missing event, or modified event detection as a compliance blocker.
3. Confirm role permissions before governance actions. No role may enable `LIVE_AUTO`.
4. Apply four-eyes control for risk-limit changes, strategy enable/disable approvals, manual-review completion, and readiness sign-off. The requester and approver must be distinct actors.
5. Run policy checks for LIVE_AUTO, real-order placement, `go_live_allowed`, evidence presence, reconciliation, monitoring, execution realism, robustness, and options-risk evidence when F&O is enabled.
6. Build the compliance checklist and resolve all failures before manual-review readiness can be considered.
7. Export `governance_compliance_json` into the evidence pack.
8. Manual review is blocked when the audit chain is invalid, a critical policy violation is unresolved, four-eyes approval is missing, evidence is not exported, or the compliance checklist fails.
9. Do not describe the audit chain as immutable or tamper-proof. It is tamper-evident only.
10. Governance controls must not enable `LIVE_AUTO`, place orders, fake compliance, or set `go_live_allowed=true`.

## Phase 19 — HA, Backup, Restore & Disaster Recovery Runbook

1. Create full backups for audit databases and runtime state before each shadow session.
2. Export audit events, governance records, evidence packs, and snapshots as separate backup objects.
3. Verify every backup checksum immediately after creation; treat checksum mismatch or missing backup as a recovery blocker.
4. Test restore into an isolated path before relying on any backup for manual-review evidence.
5. Run DR simulations for process crash, persistence failure, restart recovery, missing backup, stale backup, database loss, and snapshot corruption.
6. Validate recovery readiness: backup exists, backup is recent, checksum is valid, restore is tested, recovery path is tested, and audit chain is valid.
7. Review retention compliance for daily, weekly, and monthly backup windows.
8. Build the business continuity report and resolve every `RECOVERY_IMPROVEMENT_REQUIRED` item before manual-review readiness.
9. Export `ha_disaster_recovery_json` into the evidence pack.
10. Manual review is blocked if backup is unverified, restore is untested, audit chain is invalid, recovery readiness is not `READY`, retention is non-compliant, or any DR simulation has unresolved failures.
11. Do not claim fake HA, fake restore success, fake backup durability, or fake disaster-recovery readiness.
12. HA/DR controls must not enable `LIVE_AUTO`, place orders, or set `go_live_allowed=true`.

## Phase 20 — Final Certification & Human Trading Desk Runbook

1. Build the final evidence pack with market data, validation, paper/shadow, reconciliation, portfolio, multi-strategy, options-risk, execution-realism, monitoring, governance, compliance, HA/DR, and evidence-quality sections.
2. Run `FinalCertificationFramework` and review every `CertificationAreaReport` marked `FAIL` or `DATA_UNAVAILABLE`.
3. Generate the certification scorecard and confirm the recommendation is never `LIVE_READY`, `AUTO_APPROVED`, or `GO_LIVE`.
4. Run `EvidenceQualityValidator`; missing or stale shadow, robustness, monitoring, compliance, or HA/DR evidence blocks certification.
5. Complete analyst, risk, operations, compliance, and final-reviewer stages in `TradingDeskWorkflow`.
6. Record all review rejections with reviewer, timestamp, notes, and rejection reason.
7. Generate `FinalReadinessReport` and resolve every critical blocker before manual certification can be considered.
8. Generate `ManualCertificationPackage` JSON metadata and Markdown report for human review.
9. Export `final_certification_json` into the evidence pack.
10. Manual review remains blocked if certification package is missing, evidence quality is unacceptable, workflow is incomplete, certification has critical failures, governance/compliance fails, or HA/DR fails.
11. Do not claim fake certification, fake readiness, fake compliance, fake shadow evidence, or fake review approvals.
12. Final certification controls must not enable `LIVE_AUTO`, place orders, or set `go_live_allowed=true`.

## Critical Hardening Runbook — NO-GO Blocker Closure

1. Treat the previous institutional audit as binding: real Zerodha shadow trading remains **NO-GO** until all readiness prerequisites pass.
2. Confirm live-order hazard removal before every operator dry run:
   - Run `python scripts/no_live_order_static_scan.py`.
   - Run `python - <<'PY'\nfrom institutional_trading_platform.alpha_gate_x import assert_real_order_path_forbidden\nassert assert_real_order_path_forbidden()\nPY`.
3. Validate Zerodha credentials only through a read-only profile client. Missing profile client, revoked session, profile endpoint failure, or user mismatch must return `ZERODHA_UNAVAILABLE` and block shadow readiness.
4. Use `ZerodhaShadowFeedRunner` only as a read-only feed runner. It may subscribe, map ticks, reject malformed/duplicate ticks, emit stale-feed alerts, and shut down. It must never call broker order APIs.
5. `scripts/run_shadow_day.py` is a readiness gate. If it prints `NO_GO_SHADOW_READINESS`, do not start shadow trading. Resolve every reason first.
6. Evidence packs must include provenance for every section: source store, event range, snapshot id, audit-chain hash, generated timestamp, and verification status. Missing provenance blocks certification.
7. CI must run compile, pytest, no-live-order static scan, basic secret scan, and import smoke checks before merge.
8. Remaining real-shadow prerequisites: production KiteTicker wrapper, read-only Zerodha profile client, operator token-refresh process, persistent storage backup plan, external monitoring, incident escalation, and replay/soak testing.
9. No operator may enable `LIVE_AUTO`, submit broker orders, bypass provenance checks, or set `go_live_allowed=true`.

## Zerodha Read-Only Profile Smoke-Test Runbook

1. Confirm `LIVE_AUTO` is not configured and no operator has enabled real-order code paths.
2. Export `ZERODHA_API_KEY`, `ZERODHA_ACCESS_TOKEN`, `ZERODHA_EXPECTED_USER_ID`, and `AUDIT_DB_PATH`.
3. Run `python scripts/zerodha_profile_smoke_test.py` outside market hours first.
4. Treat `PROFILE_SMOKE_NO_GO` as a hard block. Investigate missing credentials, network failure, revoked/expired token, profile endpoint failure, or user-id mismatch.
5. Confirm the audit store contains exactly one redacted event for the attempt: `ZerodhaReadOnlyProfileSmokePassed` or `ZerodhaReadOnlyProfileSmokeFailed`.
6. Do not start WebSocket shadow trading from this step. A pass only authorizes the next smoke step: read-only WebSocket connectivity without signal generation.
7. Do not instantiate order wrappers, approval services, or broker mutation clients during the profile smoke test.
8. `go_live_allowed` must remain `false` for both pass and fail outputs.

## Zerodha Integration Audit Runbook

1. Install local development dependencies with `pip install -e '.[dev]'` so `pytest` and smoke tests are available.
2. Confirm `.env` contains `ZERODHA_API_KEY`, `ZERODHA_ACCESS_TOKEN`, `ZERODHA_EXPECTED_USER_ID`, `AUDIT_DB_PATH`, and optionally `ZERODHA_INSTRUMENT_DUMP_PATH`.
3. Run `python scripts/zerodha_profile_smoke_test.py` first. Continue only on `PROFILE_SMOKE_GO`.
4. Run `python scripts/zerodha_integration_audit.py`.
5. Treat any `FAIL` as a hard blocker. Missing instrument dump may be reported separately from broker auth; do not proceed to WebSocket smoke until imports, dependencies, environment, profile smoke, and market-data mapping are clean.
6. The next step after a clean integration audit remains read-only WebSocket connectivity smoke only. Do not start shadow trading, signal generation, approvals, previews, or any broker order flow.
