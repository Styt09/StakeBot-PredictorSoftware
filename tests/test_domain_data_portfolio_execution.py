from datetime import UTC, datetime

import pytest

from institutional_trading_platform import (
    ApprovalGate,
    AssetClass,
    DataContract,
    DataField,
    DataType,
    DatasetRecord,
    ExecutionPolicy,
    FeatureRecord,
    FinalSignalEngine,
    HealthCheck,
    Instrument,
    MarketBar,
    MetadataCatalog,
    OrderBookLevel,
    OrderBookSnapshot,
    PositionSizingRequest,
    Severity,
    SignalInput,
    SystemHealth,
    Venue,
    AuditEvent,
    inverse_volatility_weights,
    order_from_signal,
    population_stability_index,
    realized_correlation,
    rebalance_trades,
    validate_order_intent,
    volatility_targeted_position_size,
)


def _instrument() -> Instrument:
    return Instrument(symbol="RELIANCE", venue=Venue.NSE, asset_class=AssetClass.EQUITY, lot_size=1, tick_size=0.05)


def _approved_signal():
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
    return FinalSignalEngine().evaluate(signal, gates)


def test_market_bar_and_order_book_contracts_normalize_data() -> None:
    instrument = _instrument()
    bar = MarketBar(
        instrument=instrument,
        timestamp=datetime(2026, 6, 2, 9, 15, tzinfo=UTC),
        open=100.0,
        high=102.0,
        low=99.5,
        close=101.0,
        volume=10_000,
        source="unit-test",
    )

    assert instrument.instrument_id == "NSE:equity:RELIANCE"
    assert bar.to_feature_row()["instrument_id"] == instrument.instrument_id

    book = OrderBookSnapshot(
        instrument=instrument,
        timestamp=datetime(2026, 6, 2, 9, 16, tzinfo=UTC),
        bids=(OrderBookLevel(100.0, 200), OrderBookLevel(99.95, 100)),
        asks=(OrderBookLevel(100.05, 100), OrderBookLevel(100.10, 100)),
        source="unit-test",
    )

    assert book.spread == pytest.approx(0.05)
    assert book.mid_price == pytest.approx(100.025)
    assert book.order_flow_imbalance() == pytest.approx(0.2)


def test_metadata_catalog_contract_quality_lineage_and_drift() -> None:
    contract = DataContract(
        name="market_bars",
        version="1.0.0",
        owner="data-platform",
        description="Canonical OHLCV bars",
        fields=(
            DataField("instrument_id", DataType.STRING),
            DataField("close", DataType.FLOAT, minimum=0.0),
            DataField("volume", DataType.FLOAT, minimum=0.0),
        ),
    )
    catalog = MetadataCatalog()
    catalog.register_contract(contract)
    catalog.register_dataset(DatasetRecord("nse_daily_bars", contract.contract_id, "s3://bucket/nse", "data-platform"))
    catalog.register_feature(
        FeatureRecord(
            name="close_to_volume",
            version="1.0.0",
            entity="instrument_id",
            expression="close / max(volume, 1)",
            owner="research",
            source_datasets=("nse_daily_bars",),
        )
    )

    report = catalog.quality_report(
        contract.contract_id,
        [
            {"instrument_id": "NSE:equity:RELIANCE", "close": 100.0, "volume": 1000.0},
            {"instrument_id": "NSE:equity:TCS", "close": -1.0, "volume": 1000.0},
        ],
    )

    assert not report.passed
    assert report.pass_rate == pytest.approx(0.5)
    assert catalog.lineage_for_feature("close_to_volume:1.0.0")[0].name == "nse_daily_bars"
    assert population_stability_index([1, 2, 3, 4], [1, 2, 5, 6]) > 0


def test_portfolio_sizing_weights_rebalance_and_correlation() -> None:
    sizing = volatility_targeted_position_size(
        PositionSizingRequest(
            capital=100_000,
            entry_price=100,
            stop_loss=95,
            risk_budget_fraction=0.01,
            volatility=0.20,
            target_volatility=0.10,
            max_position_fraction=0.50,
        )
    )

    assert sizing.quantity == 200
    assert sizing.risk_amount == pytest.approx(1000)

    weights = inverse_volatility_weights({"A": 0.2, "B": 0.1})
    assert weights["B"] > weights["A"]
    assert sum(weights.values()) == pytest.approx(1.0)

    trades = rebalance_trades({"A": 0.4, "B": 0.6}, {"A": 0.5, "B": 0.5}, 1_000_000)
    assert trades == {"A": pytest.approx(100_000), "B": pytest.approx(-100_000)}
    assert realized_correlation([0.01, 0.02, 0.03], [0.02, 0.04, 0.06]) == pytest.approx(1.0)


def test_execution_policy_validates_signal_order_and_kill_switch_primitives() -> None:
    intent = order_from_signal(_instrument(), _approved_signal(), quantity=100)
    policy = ExecutionPolicy(max_notional=20_000, max_quantity=200, max_participation_rate=0.10, allowed_slippage_bps=100)

    assert validate_order_intent(intent, policy, last_price=100, average_daily_volume=2_000) == ()
    violations = validate_order_intent(intent, policy, last_price=80, average_daily_volume=500)
    assert "order exceeds participation-rate constraint" in violations
    assert "limit price exceeds allowed slippage" in violations


def test_audit_events_and_health_checks_are_structured() -> None:
    event = AuditEvent("signal.evaluated", "risk-engine", Severity.INFO, "Signal approved", {"decision": "BUY"})
    record = event.to_log_record()
    assert record["severity"] == "INFO"
    assert record["metadata"] == {"decision": "BUY"}

    health = SystemHealth((HealthCheck("data", True, 12.5), HealthCheck("broker", False, 50.0, "disconnected")))
    assert not health.healthy
    assert health.degraded_components == ("broker",)
    assert health.max_latency_ms == pytest.approx(50.0)
