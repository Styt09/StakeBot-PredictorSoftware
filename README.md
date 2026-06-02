# Ultimate Institutional AI Trading Platform v8.0

This repository now contains a governance-first Python foundation for an
institutional quantitative trading ecosystem focused on alpha generation,
capital preservation, risk management, portfolio optimization, execution
quality, compliance, and operational resilience.

The code is intentionally conservative: the final signal engine will only emit
`BUY` or `SELL` when every required research, risk, liquidity, compliance,
portfolio, execution, and AI-consensus gate has approved the opportunity. Any
missing or rejected control returns `NO TRADE` with rejection reasons.

## Implemented foundation

- **Tier catalog:** a data-driven registry for all 25 v8.0 capability tiers,
  including market data, data engineering, alpha research, ML/AI, derivatives,
  portfolio construction, risk, execution, governance, surveillance,
  observability, security, resilience, live trading reliability, and the meta
  decision engine.
- **Final Signal Engine v8.0:** mandatory gate checking for the platform's
  `TRADE ONLY IF` policy, confidence calibration, score validation, and final
  `BUY / SELL / HOLD / NO TRADE` decisions.
- **Risk utilities:** historical VaR, CVaR, annualized Sharpe, and fractional
  Kelly sizing helpers for risk and capital-allocation workflows.
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
