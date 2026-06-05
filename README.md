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
