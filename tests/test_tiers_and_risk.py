import pytest

from institutional_trading_platform.risk import (
    annualized_sharpe,
    conditional_value_at_risk,
    fractional_kelly,
    value_at_risk,
)
from institutional_trading_platform.tiers import build_v8_tier_catalog


def test_catalog_contains_all_v8_tiers_and_lookup() -> None:
    catalog = build_v8_tier_catalog()

    assert len(catalog.tiers) == 25
    assert catalog.by_number(25).name == "Meta Decision Engine"
    assert catalog.capability_index()["final trade approval"].number == 25


def test_catalog_readiness_score_and_missing_capabilities() -> None:
    catalog = build_v8_tier_catalog()
    implemented = ["NSE", "BSE", "Data Ingestion", "Final Trade Approval"]

    assert catalog.readiness_score(implemented) > 0
    assert "MCX" in catalog.missing_capabilities(implemented)[1]


def test_risk_metrics_are_positive_loss_values() -> None:
    returns = [-0.08, -0.03, 0.01, 0.03, 0.05, 0.07]

    assert value_at_risk(returns, 0.95) == 0.08
    assert conditional_value_at_risk(returns, 0.95) == 0.08
    assert annualized_sharpe(returns) > 0


def test_fractional_kelly_caps_negative_edges_at_zero() -> None:
    assert fractional_kelly(0.60, 2.0, 0.5) == pytest.approx(0.2)
    assert fractional_kelly(0.30, 1.0, 0.5) == 0.0
