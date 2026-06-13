from __future__ import annotations

from institutional_trading_platform.alpha_gate_x import TradingMode
from institutional_trading_platform.derivatives import (
    DATA_UNAVAILABLE,
    FNOOptionContract,
    FORiskLimits,
    IVRegime,
    OptionChainRow,
    OptionMoneyness,
    OptionPosition,
    OptionType,
    aggregate_portfolio_greeks,
    analyze_expiry_risk,
    analyze_gap_risk,
    analyze_implied_volatility,
    analyze_option_chain,
    assess_fo_risk,
    classify_option_moneyness,
)
from institutional_trading_platform.runtime import DashboardSummaryService, RuntimeConfig, ShadowRunValidator, SQLiteAuditStore
from institutional_trading_platform.runtime.evidence_pack import EvidencePackGenerator
import pytest


def _contract(strike: float = 100.0, kind: OptionType = OptionType.CALL, expiry: str = "2026-01-29", underlying: str = "NIFTY") -> FNOOptionContract:
    return FNOOptionContract(f"{underlying}{expiry}{int(strike)}{kind.value[0]}", strike, expiry, kind, 50, underlying, int(strike * 10), "NFO")


def _position(quantity: int = 1, strike: float = 100.0, kind: OptionType = OptionType.CALL, days: int = 20) -> OptionPosition:
    return OptionPosition(_contract(strike, kind), quantity, spot=100.0, implied_volatility=0.20, days_to_expiry=days)


def test_option_classification_and_chain_analytics() -> None:
    call = _contract(95, OptionType.CALL)
    put = _contract(105, OptionType.PUT)
    assert classify_option_moneyness(call, 100.0) == OptionMoneyness.ITM
    assert classify_option_moneyness(put, 100.0) == OptionMoneyness.ITM
    chain = analyze_option_chain((OptionChainRow(call, 10.0, 100, 5, 200, 0.2), OptionChainRow(put, 9.0, 150, 4, 180, 0.22)), 100.0)
    assert chain.atm_strike in {95, 105}
    assert chain.pcr == pytest.approx(1.5)
    assert chain.data_status == "OK"
    unavailable = analyze_option_chain((OptionChainRow(call, 10.0, None, 5, 200, None),), 100.0)
    assert unavailable.data_status == DATA_UNAVAILABLE


def test_greeks_aggregation_and_unavailable_inputs() -> None:
    report = aggregate_portfolio_greeks((_position(1), _position(-1, 105, OptionType.PUT)))
    assert report.data_status == "OK"
    assert isinstance(report.net_delta, float)
    missing = aggregate_portfolio_greeks((OptionPosition(_contract(), 1, spot=None, implied_volatility=0.2, days_to_expiry=10),))
    assert missing.data_status == DATA_UNAVAILABLE


def test_risk_limit_violation() -> None:
    report = assess_fo_risk((_position(10),), FORiskLimits(max_delta=1, max_lot_exposure=5, max_underlying_concentration=0.99, max_expiry_concentration=0.99))
    assert report.approved is False
    assert any("delta" in warning or "lot" in warning for warning in report.warnings)
    assert report.go_live_allowed is False


def test_iv_classification() -> None:
    low = analyze_implied_volatility(0.12, (0.10, 0.15, 0.20, 0.25, 0.30))
    high = analyze_implied_volatility(0.30, (0.10, 0.15, 0.20, 0.25, 0.30))
    assert low.regime == IVRegime.LOW_IV
    assert high.regime == IVRegime.HIGH_IV
    assert analyze_implied_volatility(None, ()).data_status == DATA_UNAVAILABLE


def test_expiry_and_gap_risk_warnings() -> None:
    expiry = analyze_expiry_risk((_position(days=1),), near_expiry_days=3)
    assert expiry.near_expiry_warning is True
    assert expiry.expiry_stress_warning is True
    gap = analyze_gap_risk(overnight_gap_pct=4.0, event_gap_pct=5.0, earnings_risk_flag=True)
    assert len(gap.warnings) == 3


def test_evidence_pack_options_risk_integration() -> None:
    store = SQLiteAuditStore(":memory:")
    risk = assess_fo_risk((_position(),), FORiskLimits(max_underlying_concentration=1, max_expiry_concentration=1))
    iv = analyze_implied_volatility(0.2, (0.1, 0.2, 0.3))
    expiry = analyze_expiry_risk((_position(days=10),))
    gap = analyze_gap_risk(1.0)
    pack = EvidencePackGenerator(store, DashboardSummaryService(store), ShadowRunValidator(store)).generate(config_summary={}, options_risk_report=risk, options_iv_analysis=iv, options_expiry_report=expiry, options_gap_report=gap)
    assert "options_risk_json" in pack.sections
    assert pack.sections["options_risk_json"]["go_live_allowed"] is False


def test_live_auto_rejected_and_no_real_order_path() -> None:
    assert not hasattr(aggregate_portfolio_greeks, "place_order")
    with pytest.raises(ValueError, match="rejects LIVE_AUTO"):
        RuntimeConfig(trading_mode=TradingMode.LIVE_AUTO)
