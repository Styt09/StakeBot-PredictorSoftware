from __future__ import annotations

from institutional_trading_platform.alpha_gate_x import TradingMode
from institutional_trading_platform.portfolio import (
    PortfolioConstructionEngine,
    PortfolioPosition,
    PortfolioRiskLimits,
    PortfolioSignalAllocation,
    kelly_fraction,
    portfolio_var_cvar_pct,
    portfolio_volatility,
)
from institutional_trading_platform.runtime import RuntimeConfig
import pytest


def _candidate(symbol: str, sector: str = "ENERGY", expected_return: float = 0.02, volatility: float = 0.15) -> PortfolioSignalAllocation:
    return PortfolioSignalAllocation(symbol, sector, "BUY", 0.8, expected_return, volatility, 100.0, 98.0, win_probability=0.58, reward_risk=1.5)


def test_kelly_fraction_is_capped_and_zero_for_negative_edge() -> None:
    assert kelly_fraction(0.6, 1.5, cap=0.20) == pytest.approx(0.20)
    assert kelly_fraction(0.3, 1.0, cap=0.25) == 0.0


def test_portfolio_engine_allocates_with_symbol_and_sector_caps() -> None:
    engine = PortfolioConstructionEngine(PortfolioRiskLimits(max_symbol_weight=0.25, max_sector_weight=0.40, risk_per_trade_fraction=0.01))
    result = engine.construct(
        capital=100_000,
        candidates=(
            _candidate("RELIANCE", "ENERGY"),
            _candidate("ONGC", "ENERGY"),
            _candidate("TCS", "IT"),
            _candidate("INFY", "IT"),
        ),
        historical_returns={"RELIANCE": (0.001, -0.001), "ONGC": (0.001, -0.001), "TCS": (0.001, -0.001), "INFY": (0.001, -0.001)},
    )

    assert result.allocations
    assert all(allocation.weight <= 0.25 for allocation in result.allocations)
    assert result.risk_report.gross_exposure <= 1.0
    assert result.go_live_allowed is False


def test_correlation_limit_rejects_candidate() -> None:
    result = PortfolioConstructionEngine(PortfolioRiskLimits(max_correlation=0.70)).construct(
        capital=100_000,
        candidates=(_candidate("RELIANCE"), _candidate("ONGC")),
        correlations={("RELIANCE", "ONGC"): 0.95},
    )

    assert "ONGC" in result.rejected_symbols
    assert any("correlation limit" in reason for reason in result.rejected_symbols["ONGC"])


def test_current_position_concentration_blocks_portfolio() -> None:
    result = PortfolioConstructionEngine(PortfolioRiskLimits(max_symbol_weight=0.20)).construct(
        capital=100_000,
        candidates=(_candidate("TCS", "IT"),),
        current_positions=(PortfolioPosition("RELIANCE", "ENERGY", 300, 100.0, 0.20),),
    )

    assert result.risk_report.approved is False
    assert any("RELIANCE exceeds symbol cap" in reason for reason in result.risk_report.reasons)


def test_portfolio_var_cvar_and_drawdown_controls() -> None:
    returns = {"RELIANCE": (-0.10, -0.08, 0.01), "TCS": (-0.05, -0.04, 0.01)}
    var, cvar = portfolio_var_cvar_pct({"RELIANCE": 0.5, "TCS": 0.5}, returns)
    assert cvar >= var > 0

    result = PortfolioConstructionEngine(PortfolioRiskLimits(max_portfolio_var_pct=1.0, max_portfolio_cvar_pct=1.0, max_drawdown_pct=5.0)).construct(
        capital=100_000,
        candidates=(_candidate("RELIANCE"), _candidate("TCS", "IT")),
        historical_returns=returns,
        equity_curve=(100_000, 90_000),
    )
    assert result.risk_report.approved is False
    assert any("VaR" in reason or "CVaR" in reason or "drawdown" in reason for reason in result.risk_report.reasons)


def test_portfolio_volatility_uses_correlations() -> None:
    low = portfolio_volatility({"A": 0.5, "B": 0.5}, {"A": 0.2, "B": 0.2}, {("A", "B"): 0.0})
    high = portfolio_volatility({"A": 0.5, "B": 0.5}, {"A": 0.2, "B": 0.2}, {("A", "B"): 0.9})
    assert high > low


def test_no_live_auto_and_no_real_order_path() -> None:
    assert not hasattr(PortfolioConstructionEngine(), "place_order")
    with pytest.raises(ValueError, match="rejects LIVE_AUTO"):
        RuntimeConfig(trading_mode=TradingMode.LIVE_AUTO)
