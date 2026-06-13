from datetime import datetime, timedelta, timezone

import pytest

from institutional_trading_platform.alpha_gate_x import AlphaSignal, FactorScores, RiskConfig, RiskGate
from institutional_trading_platform.broker.zerodha_instruments import InstrumentMappingError, ZerodhaInstrumentMapper, ZerodhaInstrumentRecord
from institutional_trading_platform.market_data_spine import (
    BacktestConfig,
    BacktestEngine,
    CandleBuilder,
    CandleTimeframe,
    DataQualityChecker,
    DataQualityStatus,
    HistoricalDataResult,
    MarketDepth,
    OHLCVCandle,
    Tick,
    UnavailableHistoricalDataLoader,
    completed_candles_for_signal,
    risk_decision_from_data_quality,
)

UTC = timezone.utc


def _ts(minute: int, second: int = 0) -> datetime:
    return datetime(2026, 1, 2, 9, minute, second, tzinfo=UTC)


def _candle(index: int, open_: float, close: float, *, volume: int = 200_000) -> OHLCVCandle:
    start = _ts(15 + index)
    return OHLCVCandle(
        symbol="RELIANCE",
        exchange="NSE",
        timeframe=CandleTimeframe.ONE_MINUTE,
        start=start,
        end=start + timedelta(minutes=1),
        open=open_,
        high=max(open_, close) + 1,
        low=min(open_, close) - 1,
        close=close,
        volume=volume,
        complete=True,
    )


def test_one_minute_candle_creation_from_ticks_and_finalization() -> None:
    builder = CandleBuilder((CandleTimeframe.ONE_MINUTE,))

    assert builder.update_tick(Tick("RELIANCE", "NSE", _ts(15, 5), 100.0, 10)) == ()
    assert builder.update_tick(Tick("RELIANCE", "NSE", _ts(15, 45), 102.0, 5)) == ()
    finalized = builder.update_tick(Tick("RELIANCE", "NSE", _ts(16, 0), 101.0, 7))

    assert len(finalized) == 1
    candle = finalized[0]
    assert candle.start == _ts(15)
    assert candle.end == _ts(16)
    assert candle.open == 100.0
    assert candle.high == 102.0
    assert candle.low == 100.0
    assert candle.close == 102.0
    assert candle.volume == 15
    assert candle.complete
    current = builder.current_candle("RELIANCE", "NSE", CandleTimeframe.ONE_MINUTE)
    assert current is not None
    assert not current.complete
    assert current.start == _ts(16)


def test_five_minute_aggregation_boundaries() -> None:
    builder = CandleBuilder((CandleTimeframe.FIVE_MINUTES,))

    builder.update_tick(Tick("RELIANCE", "NSE", _ts(15), 100.0, 1))
    builder.update_tick(Tick("RELIANCE", "NSE", _ts(19, 59), 105.0, 2))
    finalized = builder.update_tick(Tick("RELIANCE", "NSE", _ts(20), 103.0, 3))

    assert len(finalized) == 1
    assert finalized[0].start == _ts(15)
    assert finalized[0].end == _ts(20)
    assert finalized[0].open == 100.0
    assert finalized[0].high == 105.0
    assert finalized[0].close == 105.0
    assert finalized[0].volume == 3


def test_incomplete_candle_not_used_for_signal_by_default() -> None:
    complete = _candle(0, 100.0, 101.0)
    incomplete = OHLCVCandle("RELIANCE", "NSE", CandleTimeframe.ONE_MINUTE, _ts(16), _ts(17), 101, 102, 100, 101.5, 100, False)

    assert completed_candles_for_signal((complete, incomplete)) == (complete,)
    assert completed_candles_for_signal((complete, incomplete), allow_incomplete=True) == (complete, incomplete)


def test_invalid_ohlc_rejection_and_zero_volume_quality_failure() -> None:
    invalid = OHLCVCandle("RELIANCE", "NSE", CandleTimeframe.ONE_MINUTE, _ts(15), _ts(16), 100, 99, 98, 101, 0, True)
    report = DataQualityChecker().check_candle(invalid)

    assert report.status == DataQualityStatus.FAIL
    assert any("invalid OHLC" in reason for reason in report.reasons)
    assert "zero volume" in report.reasons


def test_stale_duplicate_disordered_spread_and_outlier_detection() -> None:
    checker = DataQualityChecker(stale_after=timedelta(seconds=1), max_spread_percent=0.10, max_price_jump_percent=5.0)
    first = Tick("RELIANCE", "NSE", _ts(15), 100.0, 10, tick_id="t1")
    duplicate = Tick("RELIANCE", "NSE", _ts(14, 59), 120.0, 10, tick_id="t1", depth=MarketDepth(99, 1, 101, 1))

    assert checker.check_tick(first, received_at=_ts(15)).status == DataQualityStatus.OK
    report = checker.check_tick(duplicate, received_at=_ts(15, 3))

    assert report.status == DataQualityStatus.FAIL
    assert "stale data" in report.reasons
    assert "duplicate tick" in report.reasons
    assert "timestamp disorder" in report.reasons
    assert "outlier price jump" in report.reasons
    assert "abnormal spread" in report.reasons
    assert report.risk_block_reason is not None


def test_unavailable_historical_loader_returns_data_unavailable_not_fake_data() -> None:
    result: HistoricalDataResult = UnavailableHistoricalDataLoader().load_candles("RELIANCE", CandleTimeframe.ONE_MINUTE, _ts(15), _ts(16))

    assert result.status == DataQualityStatus.DATA_UNAVAILABLE
    assert result.candles == ()
    assert result.errors == ("historical data provider unavailable",)


def test_zerodha_instrument_mapper_supports_nse_and_clear_missing_errors() -> None:
    mapper = ZerodhaInstrumentMapper((ZerodhaInstrumentRecord("RELIANCE", "NSE", 12345),))

    instrument = mapper.map_symbol("reliance", "NSE")

    assert instrument.instrument_token == 12345
    assert instrument.exchange == "NSE"
    with pytest.raises(InstrumentMappingError, match="not found"):
        mapper.map_symbol("INFY", "NSE")
    with pytest.raises(InstrumentMappingError, match="not supported"):
        mapper.map_symbol("RELIANCE", "BSE")


def test_data_quality_failure_can_be_passed_to_signal_engine_as_risk_block() -> None:
    report = DataQualityChecker().check_candle(
        OHLCVCandle("RELIANCE", "NSE", CandleTimeframe.ONE_MINUTE, _ts(15), _ts(16), 100, 99, 98, 101, 0, True)
    )

    risk = risk_decision_from_data_quality(report)

    assert risk is not None
    assert risk.status.name == "FAIL"
    assert risk.quantity == 0
    assert any("invalid OHLC" in reason for reason in risk.reasons)


def test_backtest_rejects_missing_candle_gap() -> None:
    candles = (_candle(0, 100.0, 101.0), _candle(2, 102.0, 103.0))

    result = BacktestEngine(risk_gate=RiskGate(RiskConfig(min_volume=1))).run(candles, lambda history: None)

    assert result.quality.status == DataQualityStatus.FAIL
    assert "missing candle" in result.quality.reasons



def test_backtest_no_lookahead_and_next_candle_execution() -> None:
    candles = (
        _candle(0, 100.0, 101.0),
        _candle(1, 110.0, 111.0),
        _candle(2, 120.0, 119.0),
    )
    observed_lengths: list[int] = []

    def factors(history: tuple[OHLCVCandle, ...]) -> FactorScores | None:
        observed_lengths.append(len(history))
        if len(history) == 1:
            assert history[-1].close == 101.0
            return FactorScores(0.90, 0.80, 0.75, 0.70, 0.80, 0.70)
        return None

    engine = BacktestEngine(
        risk_gate=RiskGate(RiskConfig(capital=50_000, max_order_quantity=10, min_volume=1)),
        config=BacktestConfig(starting_equity=100_000.0, brokerage_per_trade=0.0, slippage_percent=0.0),
    )
    result = engine.run(candles, factors)

    assert observed_lengths == [1, 2]
    assert result.quality.status == DataQualityStatus.OK
    assert result.metrics.total_trades == 1
    assert result.trades[0].side == AlphaSignal.BUY
    assert result.trades[0].entry_time == candles[1].start
    assert result.trades[0].entry_price == candles[1].open
    assert result.trades[0].exit_price == candles[1].close
    assert result.metrics.no_trade_percentage > 0
