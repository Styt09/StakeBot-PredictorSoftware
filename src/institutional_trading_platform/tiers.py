"""Tier catalog for the Ultimate Institutional AI Trading Platform v8.0.

The catalog is intentionally data-driven so engineering teams can wire the
same source of truth into documentation, deployment readiness checks, and
research governance workflows.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class PlatformTier:
    """A platform capability tier and its required capabilities."""

    number: int
    name: str
    capabilities: tuple[str, ...]

    @property
    def slug(self) -> str:
        """Return a stable machine-friendly identifier for the tier."""

        return self.name.lower().replace(" ", "_").replace("—", "-")


@dataclass(frozen=True)
class TierCatalog:
    """Collection of capability tiers with lookup and readiness helpers."""

    tiers: tuple[PlatformTier, ...]

    def by_number(self, number: int) -> PlatformTier:
        """Return a tier by its v8.0 tier number."""

        for tier in self.tiers:
            if tier.number == number:
                return tier
        raise KeyError(f"Unknown platform tier: {number}")

    def capability_index(self) -> dict[str, PlatformTier]:
        """Map normalized capability names to the tier that owns them."""

        return {
            capability.casefold(): tier
            for tier in self.tiers
            for capability in tier.capabilities
        }

    def missing_capabilities(self, implemented: Iterable[str]) -> dict[int, tuple[str, ...]]:
        """Return missing capabilities grouped by tier number.

        Parameters
        ----------
        implemented:
            Capability names that have a deployed implementation or accepted
            control in the current environment.
        """

        implemented_normalized = {item.casefold() for item in implemented}
        missing: dict[int, tuple[str, ...]] = {}
        for tier in self.tiers:
            tier_missing = tuple(
                capability
                for capability in tier.capabilities
                if capability.casefold() not in implemented_normalized
            )
            if tier_missing:
                missing[tier.number] = tier_missing
        return missing

    def readiness_score(self, implemented: Iterable[str]) -> float:
        """Return the percentage of catalog capabilities implemented."""

        all_capabilities = [capability for tier in self.tiers for capability in tier.capabilities]
        if not all_capabilities:
            return 0.0
        implemented_normalized = {item.casefold() for item in implemented}
        complete = sum(
            1 for capability in all_capabilities if capability.casefold() in implemented_normalized
        )
        return complete / len(all_capabilities)


def build_v8_tier_catalog() -> TierCatalog:
    """Build the v8.0 institutional trading capability catalog."""

    return TierCatalog(
        tiers=(
            PlatformTier(
                1,
                "Market Data Foundation",
                (
                    "NSE",
                    "BSE",
                    "MCX",
                    "Currency Markets",
                    "Global Indices",
                    "ETFs",
                    "Corporate Actions",
                    "Economic Data",
                    "Alternative Data",
                    "News Data",
                    "Sentiment Data",
                    "Options Chain",
                    "Futures Data",
                    "Tick Data",
                    "Order Book Data",
                    "Market Depth Data",
                ),
            ),
            PlatformTier(
                2,
                "Data Engineering",
                (
                    "Data Ingestion",
                    "Data Validation",
                    "Data Cleaning",
                    "Data Normalization",
                    "Feature Engineering",
                    "Data Quality Monitoring",
                    "Metadata Catalog",
                    "Dataset Registry",
                    "Master Data Management",
                    "Data Contracts",
                    "Data Retention Policies",
                    "Data Ownership Framework",
                ),
            ),
            PlatformTier(
                3,
                "Research Operating System",
                (
                    "Research Notebook Framework",
                    "Experiment Tracking",
                    "Dataset Registry",
                    "Feature Registry",
                    "Backtest Registry",
                    "Research Audit Trail",
                    "Research Approval Workflow",
                    "Reproducibility Framework",
                ),
            ),
            PlatformTier(
                4,
                "Alpha Research Lab",
                (
                    "Factor Models",
                    "Statistical Arbitrage",
                    "Momentum",
                    "Mean Reversion",
                    "Trend Following",
                    "Volatility Strategies",
                    "Options Alpha",
                    "Cross Asset Alpha",
                    "Alternative Data Alpha",
                    "Event Driven Alpha",
                    "Information Coefficient",
                    "IC Decay Analysis",
                    "Alpha Half Life",
                    "Signal Orthogonality",
                    "Alpha Diversification",
                    "Alpha Ensemble Optimization",
                    "Alpha Stress Testing",
                    "Alpha Robustness Testing",
                    "Walk Forward Validation",
                    "Purged K-Fold Validation",
                    "Combinatorial Purged CV",
                ),
            ),
            PlatformTier(5, "Advanced Machine Learning", ("XGBoost", "LightGBM", "CatBoost", "Random Forest", "Online Learning", "Incremental Learning", "Reinforcement Learning", "Deep Reinforcement Learning", "Meta Learning", "Transfer Learning", "Few Shot Learning", "Self Supervised Learning", "Contrastive Learning", "Active Learning")),
            PlatformTier(6, "Advanced AI", ("Transformers", "TFT", "Graph Neural Networks", "Temporal Graph Networks", "Bayesian Deep Learning", "Probabilistic Forecasting", "Uncertainty Estimation", "Explainable AI", "Causal AI", "Foundation Models", "Agentic AI Research Layer")),
            PlatformTier(7, "Regime Intelligence", ("Bayesian Regime Switching", "Markov Switching Models", "Online Regime Detection", "Dynamic Regime Weighting", "Volatility Clustering", "Liquidity Regime Detection", "Crisis Detection", "Economic Cycle Detection")),
            PlatformTier(8, "Derivatives Lab", ("Greeks Aggregation", "Volatility Surface Engine", "Volatility Forecasting", "Volatility Arbitrage", "Calendar Spread Analytics", "Dispersion Analytics", "Gamma Analytics", "Variance Analytics", "Surface Calibration")),
            PlatformTier(9, "Cross Asset Intelligence", ("Equities", "Futures", "Options", "Currency", "Commodities", "Bonds", "ETFs", "Global Indices", "Crypto Research Mode", "Correlation Engine")),
            PlatformTier(10, "Portfolio Construction", ("Mean Variance Optimization", "Risk Parity", "Hierarchical Risk Parity", "Black Litterman", "CVaR Optimization", "Bayesian Optimization", "Robust Optimization", "Multi Objective Optimization", "Dynamic Rebalancing", "Tax Aware Rebalancing")),
            PlatformTier(11, "Capital Allocation", ("Kelly", "Fractional Kelly", "Dynamic Position Sizing", "Conviction Weighting", "Volatility Targeting", "Risk Budgeting", "Capacity Constraints", "Leverage Optimization")),
            PlatformTier(12, "Risk Center", ("VaR", "CVaR", "Dynamic VaR", "Dynamic CVaR", "Stress Testing", "Liquidity Shock Simulation", "Correlation Shock Simulation", "Volatility Shock Simulation", "Margin Forecasting", "Exposure Drift Detection", "Risk Heatmaps")),
            PlatformTier(13, "Execution Engine", ("Smart Order Router", "TWAP", "VWAP", "Iceberg Orders", "Participation Algorithms", "Queue Forecasting", "Fill Probability Forecasting", "Venue Selection", "Execution Cost Forecasting", "Adaptive Execution")),
            PlatformTier(14, "Transaction Cost Analysis", ("Implementation Shortfall", "Arrival Price", "VWAP Benchmark", "TWAP Benchmark", "Participation Benchmark", "Slippage Attribution", "Market Impact Attribution", "Venue Analytics", "Broker Analytics", "Execution Quality Score")),
            PlatformTier(15, "Backtest Governance", ("Lookahead Bias Detection", "Survivorship Bias Detection", "Data Leakage Detection", "Selection Bias Detection", "Slippage Simulation", "Market Impact Simulation", "Commission Simulation", "Queue Simulation", "Corporate Action Engine", "Delisting Engine")),
            PlatformTier(16, "Alpha Governance", ("Alpha Registry", "Alpha Lifecycle", "Alpha Approval Workflow", "Alpha Capacity Analysis", "Alpha Crowding Analysis", "Alpha Decay Monitoring", "Alpha Attribution", "Alpha Retirement Engine", "Alpha PnL Decomposition")),
            PlatformTier(17, "Model Risk Management", ("Model Validation", "Independent Validation", "Benchmark Models", "Challenger Models", "Model Approval Workflow", "Model Monitoring", "Model Risk Scoring", "Model Retirement")),
            PlatformTier(18, "Surveillance", ("Spoofing Detection", "Layering Detection", "Wash Trading Detection", "Market Abuse Detection", "Manipulation Detection", "Insider Pattern Detection", "Anomaly Detection")),
            PlatformTier(19, "Compliance", ("Pre Trade Compliance", "Post Trade Compliance", "Best Execution Monitoring", "Trade Surveillance", "Audit Reporting", "Regulatory Reporting", "Record Retention", "Compliance Alerts")),
            PlatformTier(20, "Enterprise Governance", ("Strategy Approval Board", "Research Approval Board", "Risk Committee", "Investment Committee", "Audit Workflow", "Governance Dashboard")),
            PlatformTier(21, "Observability", ("Strategy Health", "Alpha Health", "Portfolio Health", "Risk Monitoring", "Drift Monitoring", "Latency Monitoring", "Resource Monitoring", "Business KPI Monitoring")),
            PlatformTier(22, "Security", ("Zero Trust Architecture", "HSM Integration", "SIEM Integration", "Threat Detection", "Vulnerability Scanning", "Security Analytics", "Incident Response Automation")),
            PlatformTier(23, "Infrastructure Resilience", ("Exchange Failover", "Broker Failover", "Vendor Failover", "Event Sourcing", "Snapshot Recovery", "Message Replay", "Chaos Testing", "Time Synchronization", "High Availability Clusters")),
            PlatformTier(24, "Live Trading Reliability", ("Position Reconciliation", "Order Reconciliation", "State Recovery", "Trade Replay", "Heartbeat Monitoring", "Circuit Breakers", "Auto Kill Switch", "Emergency Flatten Engine")),
            PlatformTier(25, "Meta Decision Engine", ("Bayesian Aggregation", "Dynamic Model Weighting", "Confidence Calibration", "Conflict Resolution", "Final Trade Approval")),
        )
    )
