"""Governance-first institutional quantitative trading platform primitives."""

from .data_engineering import (
    DataContract,
    DataField,
    DataQualityReport,
    DataType,
    DatasetRecord,
    FeatureRecord,
    MetadataCatalog,
    feature_mean,
    population_stability_index,
)
from .domain import AssetClass, Instrument, MarketBar, OrderBookLevel, OrderBookSnapshot, Venue
from .execution import ExecutionPolicy, KillSwitchState, OrderIntent, OrderSide, OrderType, order_from_signal, validate_order_intent
from .observability import AuditEvent, HealthCheck, Severity, SystemHealth
from .portfolio import (
    PositionSizingRequest,
    PositionSizingResult,
    equal_risk_contribution_weights,
    inverse_volatility_weights,
    portfolio_expected_return,
    realized_correlation,
    rebalance_trades,
    volatility_targeted_position_size,
)
from .signal_engine import (
    ApprovalGate,
    FinalSignalEngine,
    MarketDecision,
    SignalInput,
    SignalOutput,
)
from .tiers import PlatformTier, TierCatalog, build_v8_tier_catalog

__all__ = [
    "ApprovalGate",
    "AssetClass",
    "AuditEvent",
    "DataContract",
    "DataField",
    "DataQualityReport",
    "DataType",
    "DatasetRecord",
    "ExecutionPolicy",
    "FeatureRecord",
    "FinalSignalEngine",
    "HealthCheck",
    "Instrument",
    "KillSwitchState",
    "MarketBar",
    "MarketDecision",
    "MetadataCatalog",
    "OrderBookLevel",
    "OrderBookSnapshot",
    "OrderIntent",
    "OrderSide",
    "OrderType",
    "PlatformTier",
    "PositionSizingRequest",
    "PositionSizingResult",
    "Severity",
    "SignalInput",
    "SignalOutput",
    "SystemHealth",
    "TierCatalog",
    "Venue",
    "build_v8_tier_catalog",
    "equal_risk_contribution_weights",
    "feature_mean",
    "inverse_volatility_weights",
    "order_from_signal",
    "population_stability_index",
    "portfolio_expected_return",
    "realized_correlation",
    "rebalance_trades",
    "validate_order_intent",
    "volatility_targeted_position_size",
]
