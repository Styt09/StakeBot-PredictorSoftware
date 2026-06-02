from institutional_trading_platform import ApprovalGate, FinalSignalEngine, MarketDecision, SignalInput


def _approved_gates() -> tuple[ApprovalGate, ...]:
    return tuple(ApprovalGate(name, True) for name in FinalSignalEngine.REQUIRED_GATES)


def _signal_input(**overrides) -> SignalInput:
    base = {
        "expected_move": 0.035,
        "expected_sharpe": 1.7,
        "expected_sortino": 2.1,
        "expected_drawdown": 0.04,
        "probability_of_profit": 0.68,
        "bullish_probability": 0.72,
        "bearish_probability": 0.28,
        "entry": 100.0,
        "stop_loss": 96.0,
        "targets": (104.0, 108.0, 112.0, 116.0),
        "dynamic_exit": 101.5,
        "risk_reward": 3.0,
        "position_size": 250.0,
        "capital_allocation": 0.08,
        "scores": {score: 0.74 for score in FinalSignalEngine.REQUIRED_SCORES},
        "model_votes": {"alpha": 0.76, "risk": 0.71, "macro": 0.69},
    }
    base.update(overrides)
    return SignalInput(**base)


def test_engine_returns_buy_when_all_gates_and_scores_pass() -> None:
    output = FinalSignalEngine().evaluate(_signal_input(), _approved_gates())

    assert output.decision == MarketDecision.BUY
    assert output.is_tradeable
    assert output.entry == 100.0
    assert output.rejected_gates == ()


def test_engine_blocks_trade_when_any_required_gate_fails() -> None:
    gates = tuple(
        ApprovalGate(gate.name, False, "liquidity shock")
        if gate.name == "Liquidity Approved"
        else gate
        for gate in _approved_gates()
    )

    output = FinalSignalEngine().evaluate(_signal_input(), gates)

    assert output.decision == MarketDecision.NO_TRADE
    assert not output.is_tradeable
    assert output.position_size == 0.0
    assert any(gate.name == "Liquidity Approved" for gate in output.rejected_gates)


def test_engine_blocks_trade_when_required_score_is_missing() -> None:
    scores = {score: 0.8 for score in FinalSignalEngine.REQUIRED_SCORES if score != "risk"}

    output = FinalSignalEngine().evaluate(_signal_input(scores=scores), _approved_gates())

    assert output.decision == MarketDecision.NO_TRADE
    assert any(gate.name == "Risk Score" for gate in output.rejected_gates)


def test_engine_returns_sell_for_bearish_approved_signal() -> None:
    output = FinalSignalEngine().evaluate(
        _signal_input(bullish_probability=0.22, bearish_probability=0.78),
        _approved_gates(),
    )

    assert output.decision == MarketDecision.SELL
