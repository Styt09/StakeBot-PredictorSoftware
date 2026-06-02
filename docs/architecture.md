# Architecture Report

## Target architecture

```mermaid
flowchart LR
    Vendors[Market/Data Vendors] --> Adapters[Data Adapters]
    Adapters --> Contracts[Data Contracts]
    Contracts --> Quality[Data Quality + Drift]
    Quality --> Catalog[Metadata Catalog]
    Catalog --> FeatureStore[Feature Store]
    FeatureStore --> Research[Research OS + Alpha Lab]
    Research --> Models[ML/AI/LLM/Regime Models]
    Models --> Meta[Meta Decision Engine]
    Meta --> Signal[Final Signal Engine]
    Signal --> Risk[Risk Center]
    Risk --> Portfolio[Portfolio Construction]
    Portfolio --> Execution[Execution Engine]
    Execution --> Broker[Broker Adapter: Zerodha Kite]
    Execution --> TCA[Transaction Cost Analysis]
    Signal --> Audit[Audit Trail]
    Risk --> Audit
    Execution --> Audit
    Audit --> Observability[Monitoring + Health + Alerts]
```

## Implemented module map

```mermaid
flowchart TB
    Domain[domain.py\nInstrument, MarketBar, OrderBook] --> Data[data_engineering.py\nContracts, Catalog, Quality, PSI]
    Domain --> Execution[execution.py\nOrderIntent, Policy, KillSwitch]
    Signal[signal_engine.py\nFinal approval] --> Execution
    Portfolio[portfolio.py\nSizing, Weights, Rebalance] --> Signal
    Risk[risk.py\nVaR, CVaR, Sharpe, Kelly] --> Portfolio
    Observability[observability.py\nAuditEvent, HealthCheck] --> Ops[Operations]
    Tiers[tiers.py\n25-tier catalog] --> Roadmap[Roadmap governance]
```

## Integration boundaries

- All external payloads must be normalized into `Instrument`, `MarketBar`, or `OrderBookSnapshot` before downstream use.
- All datasets and feature views must declare a `DataContract` and be registered in `MetadataCatalog`.
- The final signal engine remains the only component allowed to emit executable BUY/SELL signals.
- Execution adapters must accept broker-neutral `OrderIntent` objects and enforce `ExecutionPolicy` and `KillSwitchState` before order placement.
- Operational events should be emitted as `AuditEvent` records and health probes as `HealthCheck` objects.

## Expanded executable tier map

```mermaid
flowchart TB
    ResearchOS[research.py\nResearch OS] --> AlphaLab[alpha.py\nAlpha Lab + Science]
    AlphaLab --> Micro[microstructure.py\nMicrostructure Alpha]
    AlphaLab --> MLAI[ml_ai.py\nML/AI/LLM + Ensemble]
    MLAI --> Regime[regime.py\nRegime Intelligence]
    Regime --> Meta[meta_decision.py\nTier 25 Meta Engine]
    Deriv[derivatives.py\nDerivatives Lab] --> Meta
    Risk[risk.py\nDynamic Risk Center] --> Meta
    Portfolio[portfolio.py\nPortfolio + Capital Allocation] --> Meta
    Meta --> Signal[signal_engine.py\nFinal Signal Engine]
    Signal --> Execution[execution.py\nExecution Algorithms + Order Manager]
    Execution --> TCA[tca_governance.py\nTCA + Governance]
    TCA --> Observability[observability.py\nAudit + Health]
```
