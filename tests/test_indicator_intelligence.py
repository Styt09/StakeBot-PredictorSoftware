from datetime import datetime, timedelta, timezone

from institutional_trading_platform.alpha_gate_x import AlphaSignal, RiskDecision, RiskStatus
from institutional_trading_platform.alpha_gate_x_indicators import IndicatorContext, IndicatorSignalComposer, TradingProfile
from institutional_trading_platform.indicators.atr import atr, atr_stop_loss, atr_targets
from institutional_trading_platform.indicators.liquidity_sweep import liquidity_sweep_score
from institutional_trading_platform.indicators.market_breadth import MarketBreadthSnapshot, market_breadth_score
from institutional_trading_platform.indicators.order_book_imbalance import order_book_imbalance_score
from institutional_trading_platform.indicators.trend_regime import TrendRegimeLabel, trend_regime
from institutional_trading_platform.indicators.volume_confirmation import volume_confirmation_score
from institutional_trading_platform.indicators.vwap import session_vwap, vwap_pressure_score
from institutional_trading_platform.market_data_spine import (
    BacktestConfig,
    BacktestEngine,
    CandleTimeframe,
    DataQualityReport,
    DataQualityStatus,
    MarketDepth,
    OHLCVCandle,
)

UTC = timezone.utc


def _candle(index: int, open_: float, high: float, low: float, close: float, volume: int = 1000, timeframe: CandleTimeframe = CandleTimeframe.ONE_MINUTE, complete: bool = True) -> OHLCVCandle:
    start = datetime(2026, 1, 2, 9, 15, tzinfo=UTC) + index * timeframe.duration
    return OHLCVCandle("RELIANCE", "NSE", timeframe, start, start + timeframe.duration, open_, high, low, close, volume, complete)


def _trend_candles(direction: str = "up", timeframe: CandleTimeframe = CandleTimeframe.FIFTEEN_MINUTES) -> tuple[OHLCVCandle, ...]:
    candles = []
    for index in range(60):
        base = 100 + index * 2 if direction == "up" else 220 - index * 2
        close = base + 1 if direction == "up" else base - 1
        candles.append(_candle(index, base, max(base, close) + 1, min(base, close) - 1, close, 1000, timeframe))
    return tuple(candles)


def _range_candles() -> tuple[OHLCVCandle, ...]:
    return tuple(_candle(index, 100, 102, 98, 100 + (0.2 if index % 2 else -0.2), 1000, CandleTimeframe.FIFTEEN_MINUTES) for index in range(60))


def _danger_candles() -> tuple[OHLCVCandle, ...]:
    return tuple(_candle(index, 100 + index, 130 + index, 70 + index, 101 + index, 1000, CandleTimeframe.FIFTEEN_MINUTES) for index in range(60))


def _entry_candles(timeframe: CandleTimeframe = CandleTimeframe.FIVE_MINUTES) -> tuple[OHLCVCandle, ...]:
    candles = [_candle(index, 100 + index, 101 + index, 99 + index, 100.5 + index, 1000, timeframe) for index in range(24)]
    candles.append(_candle(24, 126, 130, 98, 129, 4000, timeframe))
    return tuple(candles)


def test_vwap_calculation_and_bullish_bearish_scores() -> None:
    bullish = (_candle(0, 100, 101, 99, 100, 100), _candle(1, 100, 102, 99, 101, 100), _candle(2, 106, 108, 105, 108, 300))
    bearish = (_candle(0, 100, 101, 99, 100, 100), _candle(1, 100, 101, 98, 99, 100), _candle(2, 94, 95, 92, 92, 300))

    assert session_vwap(bullish) is not None
    assert vwap_pressure_score(bullish).score > 0
    assert vwap_pressure_score(bearish).score < 0


def test_atr_calculation_and_insufficient_data() -> None:
    candles = (_candle(0, 10, 12, 9, 11), _candle(1, 11, 15, 10, 14), _candle(2, 14, 16, 13, 15))

    result = atr(candles, period=2)
    unavailable = atr(candles[:1], period=14)

    assert result.score == 4.0
    assert unavailable.status == DataQualityStatus.DATA_UNAVAILABLE
    assert atr_stop_loss(100, "BUY", 4) == 94
    assert atr_targets(100, "BUY", 4) == (108, 112)


def test_trend_regime_bullish_bearish_range_and_danger() -> None:
    bullish = trend_regime(_trend_candles("up"))
    bearish = trend_regime(_trend_candles("down"))
    ranging = trend_regime(_range_candles())
    danger = trend_regime(_danger_candles(), danger_atr_percent=8)

    assert bullish.score > 0
    assert TrendRegimeLabel.BULLISH_TREND.value in bullish.reasons
    assert bearish.score < 0
    assert TrendRegimeLabel.BEARISH_TREND.value in bearish.reasons
    assert ranging.score == 0
    assert TrendRegimeLabel.RANGE.value in ranging.reasons
    assert danger.score == -1.0
    assert TrendRegimeLabel.DANGER.value in danger.reasons


def test_liquidity_sweep_bullish_and_bearish() -> None:
    base = tuple(_candle(index, 100, 105, 95, 100) for index in range(5))
    bullish = base + (_candle(5, 99, 102, 94, 101),)
    bearish = base + (_candle(5, 101, 106, 98, 104),)

    assert liquidity_sweep_score(bullish).score > 0
    assert liquidity_sweep_score(bearish).score < 0


def test_volume_expansion_and_low_volume_warning() -> None:
    base = tuple(_candle(index, 100, 101, 99, 100.5, 1000) for index in range(20))
    expansion = base + (_candle(20, 101, 103, 100, 103, 3000),)
    low_volume = base + (_candle(20, 101, 102, 100, 101.5, 100),)

    assert volume_confirmation_score(expansion).score > 0
    warning = volume_confirmation_score(low_volume)
    assert warning.score == 0
    assert "low volume warning" in warning.reasons[0]


def test_order_book_imbalance_positive_negative_and_unavailable() -> None:
    positive = order_book_imbalance_score(MarketDepth(100, 900, 100.1, 100))
    negative = order_book_imbalance_score(MarketDepth(100, 100, 100.1, 900))
    unavailable = order_book_imbalance_score(None)

    assert positive.score > 0
    assert negative.score < 0
    assert unavailable.status == DataQualityStatus.DATA_UNAVAILABLE


def test_market_breadth_scores_and_unavailable() -> None:
    positive = market_breadth_score(MarketBreadthSnapshot(80, 20, 0))
    negative = market_breadth_score(MarketBreadthSnapshot(20, 80, 0))
    unavailable = market_breadth_score(None)

    assert positive.score > 0
    assert negative.score < 0
    assert unavailable.status == DataQualityStatus.DATA_UNAVAILABLE


def test_final_weighted_score_component_reasons_and_confidence_reduction() -> None:
    risk = RiskDecision(RiskStatus.PASS, 10, 100, ())
    composer = IndicatorSignalComposer()
    full = composer.intraday_signal(
        symbol="RELIANCE",
        exchange="NSE",
        one_minute=(),
        five_minute=_entry_candles(),
        fifteen_minute=_trend_candles("up"),
        risk_decision=risk,
        context=IndicatorContext(depth=MarketDepth(100, 900, 100.05, 100), breadth=MarketBreadthSnapshot(80, 20)),
        correlation_id="phase3-full",
    )
    missing = composer.intraday_signal(
        symbol="RELIANCE",
        exchange="NSE",
        one_minute=(),
        five_minute=_entry_candles(),
        fifteen_minute=_trend_candles("up"),
        risk_decision=risk,
        context=IndicatorContext(),
        correlation_id="phase3-missing",
    )

    assert full.signal == AlphaSignal.BUY
    assert full.final_score > 0.72
    assert full.confidence_grade.value in {"A", "B"}
    assert full.component_scores["trend_regime"] > 0
    assert any(reason.startswith("trend_regime:") for reason in full.reasons)
    assert "order_book_imbalance" in missing.unavailable_components
    assert "market_breadth" in missing.unavailable_components
    assert missing.confidence < full.confidence


def test_danger_and_bad_data_quality_force_no_trade() -> None:
    risk = RiskDecision(RiskStatus.PASS, 10, 100, ())
    composer = IndicatorSignalComposer()
    danger = composer.intraday_signal(
        symbol="RELIANCE",
        exchange="NSE",
        one_minute=(),
        five_minute=_entry_candles(),
        fifteen_minute=_danger_candles(),
        risk_decision=risk,
        context=IndicatorContext(depth=MarketDepth(100, 900, 100.05, 100), breadth=MarketBreadthSnapshot(80, 20)),
    )
    bad_data = composer.intraday_signal(
        symbol="RELIANCE",
        exchange="NSE",
        one_minute=(),
        five_minute=_entry_candles(),
        fifteen_minute=_trend_candles("up"),
        risk_decision=risk,
        context=IndicatorContext(data_quality=DataQualityReport(DataQualityStatus.FAIL, ("stale data",))),
    )

    assert danger.signal == AlphaSignal.NO_TRADE
    assert bad_data.signal == AlphaSignal.NO_TRADE
    assert bad_data.risk_status == RiskStatus.FAIL


def test_intraday_and_swing_profiles_use_expected_timeframes_and_ignore_incomplete() -> None:
    risk = RiskDecision(RiskStatus.PASS, 10, 100, ())
    composer = IndicatorSignalComposer()
    incomplete = _candle(99, 200, 250, 50, 240, 10_000, CandleTimeframe.FIVE_MINUTES, complete=False)
    intraday = composer.intraday_signal(
        symbol="RELIANCE",
        exchange="NSE",
        one_minute=(_candle(0, 1, 2, 1, 2),),
        five_minute=_entry_candles() + (incomplete,),
        fifteen_minute=_trend_candles("up"),
        risk_decision=risk,
        context=IndicatorContext(depth=MarketDepth(100, 900, 100.05, 100), breadth=MarketBreadthSnapshot(80, 20)),
    )
    swing = composer.swing_signal(
        symbol="RELIANCE",
        exchange="NSE",
        daily=_trend_candles("up", CandleTimeframe.DAILY),
        hourly=_entry_candles(CandleTimeframe.ONE_HOUR),
        risk_decision=risk,
        context=IndicatorContext(depth=MarketDepth(100, 900, 100.05, 100), breadth=MarketBreadthSnapshot(80, 20)),
    )

    assert intraday.trading_profile == TradingProfile.INTRADAY
    assert intraday.timeframe == "5m"
    assert intraday.entry_reference != incomplete.close
    assert swing.trading_profile == TradingProfile.SWING
    assert swing.timeframe == "1H"
    assert swing.expected_move is not None


def test_phase3_backtest_still_avoids_lookahead_and_executes_next_open() -> None:
    candles = tuple(_candle(index, 100 + index, 101 + index, 99 + index, 100.5 + index, 1000) for index in range(3))
    observed_lengths: list[int] = []

    class Signal:
        signal = AlphaSignal.BUY
        stop_loss = None
        target_1 = None

    def scorer(history: tuple[OHLCVCandle, ...]) -> object:
        observed_lengths.append(len(history))
        assert len(history) <= 2
        return Signal() if len(history) == 1 else object()

    result = BacktestEngine(config=BacktestConfig(brokerage_per_trade=0, slippage_percent=0)).run_with_indicator_scoring(candles, scorer)

    assert observed_lengths == [1, 2]
    assert result.metrics.total_trades == 1
    assert result.trades[0].entry_time == candles[1].start
    assert result.trades[0].entry_price == candles[1].open
