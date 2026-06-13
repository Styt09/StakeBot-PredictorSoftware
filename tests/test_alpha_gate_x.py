from datetime import time

import pytest

from institutional_trading_platform.alpha_gate_x import (
    AlphaGateXEngine,
    AlphaGateXSettings,
    AlphaSignal,
    FactorScores,
    MarketRegime,
    OrderRouter,
    OrderState,
    OrderStateMachine,
    RiskConfig,
    RiskContext,
    RiskGate,
    RiskStatus,
    TradingMode,
)


def _passing_risk() -> tuple[RiskGate, RiskContext]:
    gate = RiskGate(
        RiskConfig(
            capital=50_000,
            risk_per_trade_percent=0.5,
            max_daily_loss_percent=1.0,
            max_trades_per_day=5,
            max_order_quantity=50,
            max_open_positions=2,
            min_volume=10_000,
        )
    )
    context = RiskContext(average_volume=25_000, spread_percent=0.02, realized_volatility=0.02)
    return gate, context


def test_alpha_gate_x_buy_signal_uses_weighted_formula_and_risk_pass() -> None:
    gate, context = _passing_risk()
    risk = gate.assess(entry=100.0, stop_loss=95.0, context=context)
    factors = FactorScores(
        trend_regime=0.90,
        liquidity_sweep=0.80,
        vwap_pressure=0.75,
        order_book_imbalance=0.70,
        volume_confirmation=0.80,
        market_breadth=0.70,
    )

    signal = AlphaGateXEngine().evaluate(
        symbol="RELIANCE",
        exchange="NSE",
        timeframe="5m",
        factors=factors,
        risk_decision=risk,
        market_regime=MarketRegime.BULLISH,
        entry=100.0,
        stop_loss=95.0,
        target_1=110.0,
        target_2=115.0,
        correlation_id="cid-buy",
    )

    assert risk.status == RiskStatus.PASS
    assert risk.quantity == 50
    assert signal.signal == AlphaSignal.BUY
    assert signal.final_score == 0.7925
    assert signal.is_actionable
    assert signal.correlation_id == "cid-buy"


def test_alpha_gate_x_sell_signal_and_danger_regime_blocks_trade() -> None:
    gate, context = _passing_risk()
    risk = gate.assess(entry=100.0, stop_loss=105.0, context=context)
    bearish = FactorScores(-0.90, -0.80, -0.75, -0.80, -0.75, -0.70)

    sell = AlphaGateXEngine().evaluate(
        symbol="RELIANCE",
        exchange="NSE",
        timeframe="5m",
        factors=bearish,
        risk_decision=risk,
        market_regime=MarketRegime.BEARISH,
        entry=100.0,
        stop_loss=105.0,
        target_1=95.0,
        target_2=90.0,
    )
    blocked = AlphaGateXEngine().evaluate(
        symbol="RELIANCE",
        exchange="NSE",
        timeframe="5m",
        factors=bearish,
        risk_decision=risk,
        market_regime=MarketRegime.DANGER,
        entry=100.0,
        stop_loss=105.0,
        target_1=95.0,
        target_2=90.0,
    )

    assert sell.signal == AlphaSignal.SELL
    assert blocked.signal == AlphaSignal.NO_TRADE
    assert "market regime danger" in blocked.reasons


def test_risk_gate_blocks_kill_switch_stale_data_daily_loss_and_first_five_minutes() -> None:
    gate, _ = _passing_risk()
    risk = gate.assess(
        entry=100.0,
        stop_loss=95.0,
        context=RiskContext(
            daily_realized_loss=500,
            kill_switch_active=True,
            market_data_stale=True,
            average_volume=25_000,
            current_time=time(9, 16),
        ),
    )

    assert risk.status == RiskStatus.FAIL
    assert risk.quantity == 0
    assert "kill switch active" in risk.reasons
    assert "market data stale" in risk.reasons
    assert "daily loss limit hit" in risk.reasons
    assert "first 5 minutes blocked" in risk.reasons


def test_live_auto_requires_explicit_live_flag_and_paper_is_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TRADING_MODE", raising=False)
    monkeypatch.delenv("LIVE_TRADING", raising=False)
    default_settings = AlphaGateXSettings.from_env()

    assert default_settings.trading_mode == TradingMode.PAPER_TRADING
    assert not default_settings.live_orders_enabled

    monkeypatch.setenv("TRADING_MODE", "LIVE_AUTO")
    monkeypatch.setenv("LIVE_TRADING", "false")
    with pytest.raises(ValueError, match="LIVE_AUTO requires LIVE_TRADING=true"):
        AlphaGateXSettings.from_env()


def test_order_router_paper_fill_and_duplicate_prevention() -> None:
    gate, context = _passing_risk()
    risk = gate.assess(entry=100.0, stop_loss=95.0, context=context)
    signal = AlphaGateXEngine().evaluate(
        symbol="RELIANCE",
        exchange="NSE",
        timeframe="5m",
        factors=FactorScores(0.90, 0.80, 0.75, 0.70, 0.80, 0.70),
        risk_decision=risk,
        market_regime=MarketRegime.BULLISH,
        entry=100.0,
        stop_loss=95.0,
        target_1=110.0,
        target_2=115.0,
        correlation_id="cid-dup",
    )
    router = OrderRouter(AlphaGateXSettings())

    first = router.route(signal, risk)
    second = router.route(signal, risk)

    assert first.status == OrderState.ORDER_FILLED
    assert first.broker_order_id == "paper-cid-dup"
    assert second.status == OrderState.ORDER_REJECTED
    assert second.rejection_reason == "duplicate order blocked"


def test_approval_mode_requires_manual_approval_before_paper_fill() -> None:
    gate, context = _passing_risk()
    risk = gate.assess(entry=100.0, stop_loss=95.0, context=context)
    signal = AlphaGateXEngine().evaluate(
        symbol="RELIANCE",
        exchange="NSE",
        timeframe="5m",
        factors=FactorScores(0.90, 0.80, 0.75, 0.70, 0.80, 0.70),
        risk_decision=risk,
        market_regime=MarketRegime.BULLISH,
        entry=100.0,
        stop_loss=95.0,
        target_1=110.0,
        target_2=115.0,
        correlation_id="cid-approval",
    )
    router = OrderRouter(AlphaGateXSettings(trading_mode=TradingMode.APPROVAL_MODE))

    pending = router.route(signal, risk)
    approved = router.route(signal, risk, manual_approved=True)

    assert pending.status == OrderState.RISK_APPROVED
    assert pending.rejection_reason == "manual approval required"
    assert approved.status == OrderState.ORDER_FILLED



def test_order_state_machine_rejects_invalid_transition() -> None:
    machine = OrderStateMachine()

    assert machine.transition(OrderState.RISK_CHECK_PENDING) == OrderState.RISK_CHECK_PENDING
    assert machine.transition(OrderState.RISK_APPROVED) == OrderState.RISK_APPROVED
    with pytest.raises(ValueError, match="invalid transition"):
        machine.transition(OrderState.POSITION_OPEN)
