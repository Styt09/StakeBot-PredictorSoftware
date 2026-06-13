from datetime import datetime, timedelta, timezone
import json

from institutional_trading_platform.alpha_gate_x import AlphaSignal
from institutional_trading_platform.market_data_spine import BacktestConfig, BacktestEngine, CandleTimeframe, OHLCVCandle, TradeRecord
from institutional_trading_platform.validation import (
    GoLiveGateConfig,
    RiskEventRecord,
    analyze_by_regime,
    analyze_by_symbol,
    analyze_by_time,
    build_equity_curve,
    build_risk_report,
    calculate_performance_metrics,
    create_validation_report,
    daily_pnl,
    drawdown_curve,
    equity_curve_to_csv,
    evaluate_go_live_gate,
    max_drawdown,
    monthly_pnl,
    report_to_json,
    report_to_markdown,
    trades_to_csv,
    walk_forward_splits,
)

UTC = timezone.utc


def _trade(index: int, pnl: float, symbol: str = "RELIANCE") -> TradeRecord:
    entry = datetime(2026, 1, 5, 9 + (index % 6), 15, tzinfo=UTC) + timedelta(days=index)
    return TradeRecord(symbol, AlphaSignal.BUY, entry, entry + timedelta(minutes=5), 100.0, 100.0 + pnl, 1, pnl)


def _candle(index: int, symbol: str = "RELIANCE") -> OHLCVCandle:
    start = datetime(2026, 1, 5, 9, 15, tzinfo=UTC) + timedelta(minutes=index)
    return OHLCVCandle(symbol, "NSE", CandleTimeframe.ONE_MINUTE, start, start + timedelta(minutes=1), 100 + index, 101 + index, 99 + index, 100.5 + index, 1000, True)


def test_metrics_win_rate_profit_factor_drawdown_expectancy_and_ratios() -> None:
    trades = (_trade(0, 100), _trade(1, -50), _trade(2, 150), _trade(3, -25))
    equity = build_equity_curve(1000, trades)
    metrics = calculate_performance_metrics(trades, equity, initial_capital=1000, opportunities=8, no_trade_count=4, brokerage_cost=80, slippage_cost=10)

    assert metrics.total_trades == 4
    assert metrics.winning_trades == 2
    assert metrics.losing_trades == 2
    assert metrics.win_rate == 50.0
    assert metrics.gross_profit == 250
    assert metrics.gross_loss == 75
    assert round(metrics.profit_factor, 4) == round(250 / 75, 4)
    assert metrics.expectancy == 43.75
    assert max_drawdown(equity)[0] == 50
    assert metrics.sharpe_ratio != 0
    assert metrics.sortino_ratio != 0
    assert metrics.brokerage_cost == 80
    assert metrics.slippage_cost == 10


def test_zero_all_winning_and_all_losing_trade_reports_are_safe() -> None:
    zero = calculate_performance_metrics((), (1000,), initial_capital=1000)
    winners = calculate_performance_metrics((_trade(0, 10), _trade(1, 20)), (1000, 1010, 1030), initial_capital=1000)
    losers = calculate_performance_metrics((_trade(0, -10), _trade(1, -20)), (1000, 990, 970), initial_capital=1000)

    assert zero.total_trades == 0
    assert zero.profit_factor == 0.0
    assert winners.profit_factor == float("inf")
    assert winners.max_consecutive_wins == 2
    assert losers.profit_factor == 0.0
    assert losers.max_consecutive_losses == 2


def test_equity_drawdown_daily_and_monthly_curves() -> None:
    trades = (_trade(0, 100), _trade(1, -25))
    equity = build_equity_curve(1000, trades)

    assert equity == (1000, 1100, 1075)
    assert drawdown_curve(equity) == (0, 0, 25)
    assert daily_pnl(trades)[trades[0].exit_time.date().isoformat()] == 100
    assert monthly_pnl(trades)["2026-01"] == 75


def test_walk_forward_split_no_leakage() -> None:
    splits = walk_forward_splits(total_length=10, train_window=4, test_window=2)

    assert splits == ((0, 4, 4, 6), (2, 6, 6, 8), (4, 8, 8, 10))
    assert all(train_end == test_start for _, train_end, test_start, _ in splits)


def test_regime_symbol_time_and_risk_aggregation() -> None:
    trades = (_trade(0, 100, "RELIANCE"), _trade(1, -50, "INFY"), _trade(2, 25, "RELIANCE"))
    regimes = analyze_by_regime(trades, {0: "BULLISH_TREND", 1: "RANGE", 2: "BULLISH_TREND"}, ["DANGER", "RANGE"])
    symbols = analyze_by_symbol(trades)
    times = analyze_by_time(trades, first_5_minutes_blocked=3)
    risk = build_risk_report((RiskEventRecord("daily loss limit hit"), RiskEventRecord("stale data"), RiskEventRecord("DATA_UNAVAILABLE breadth")))

    assert regimes["BULLISH_TREND"].trades == 2
    assert regimes["RANGE"].no_trade_frequency == 1
    assert symbols.best_symbol == "RELIANCE"
    assert symbols.worst_symbol == "INFY"
    assert times.first_5_minutes_blocked_impact == 3
    assert risk.daily_loss_limit_breaches == 1
    assert risk.stale_data_block_count == 1
    assert risk.data_unavailable_count == 1


def test_go_live_gate_pass_and_fail_cases() -> None:
    pass_trades = tuple(_trade(i, 100 if i % 2 == 0 else -40) for i in range(120))
    pass_metrics = calculate_performance_metrics(pass_trades, build_equity_curve(100_000, pass_trades), initial_capital=100_000, opportunities=150, no_trade_count=30)
    empty_risk = build_risk_report(())
    pass_gate = evaluate_go_live_gate(pass_metrics, empty_risk, config=GoLiveGateConfig(maximum_losing_streak=10))

    low_trades = evaluate_go_live_gate(calculate_performance_metrics(pass_trades[:10], build_equity_curve(100_000, pass_trades[:10]), initial_capital=100_000), empty_risk)
    high_drawdown_metrics = calculate_performance_metrics(tuple(_trade(i, -1000) for i in range(120)), tuple(100_000 - i * 1000 for i in range(121)), initial_capital=100_000)
    high_drawdown = evaluate_go_live_gate(high_drawdown_metrics, empty_risk)
    low_pf_metrics = calculate_performance_metrics(tuple(_trade(i, 10 if i % 2 == 0 else -100) for i in range(120)), build_equity_curve(100_000, tuple(_trade(i, 10 if i % 2 == 0 else -100) for i in range(120))), initial_capital=100_000)
    low_pf = evaluate_go_live_gate(low_pf_metrics, empty_risk)

    assert pass_gate.verdict == "PASS"
    assert pass_gate.go_live_allowed
    assert low_trades.verdict == "NEEDS_MORE_DATA"
    assert any("below minimum" in reason for reason in low_trades.failure_reasons)
    assert any("drawdown" in reason for reason in high_drawdown.failure_reasons)
    assert any("profit factor" in reason for reason in low_pf.failure_reasons)


def test_report_json_markdown_and_csv_exports() -> None:
    trades = tuple(_trade(i, 100 if i % 2 == 0 else -40) for i in range(120))
    equity = build_equity_curve(100_000, trades)
    metrics = calculate_performance_metrics(trades, equity, initial_capital=100_000, opportunities=150, no_trade_count=30)
    risk = build_risk_report(())
    report = create_validation_report(
        strategy_name="ALPHA-GATE X",
        trading_profile="INTRADAY",
        symbols=("RELIANCE",),
        timeframe="5m",
        start_date=trades[0].entry_time,
        end_date=trades[-1].exit_time,
        initial_capital=100_000,
        metrics=metrics,
        equity_curve=equity,
        walk_forward_results=None,
        regime_analysis={},
        symbol_analysis={},
        time_analysis={},
        risk_report=risk,
        gate_config=GoLiveGateConfig(maximum_losing_streak=10),
    )

    payload = json.loads(report_to_json(report))
    markdown = report_to_markdown(report)
    trade_csv = trades_to_csv(trades[:1])
    equity_csv = equity_curve_to_csv(equity[:2])

    assert payload["strategy_name"] == "ALPHA-GATE X"
    assert "Verdict" in markdown
    assert trade_csv.startswith("symbol,side,entry_time")
    assert "RELIANCE" in trade_csv
    assert equity_csv.startswith("step,equity")


def test_multi_symbol_backtest_outputs_audit_records() -> None:
    candles = {"RELIANCE": tuple(_candle(i, "RELIANCE") for i in range(3)), "BAD": (_candle(0, "BAD"), _candle(2, "BAD"))}

    class Signal:
        signal = AlphaSignal.BUY

    result = BacktestEngine(config=BacktestConfig(brokerage_per_trade=0, slippage_percent=0)).run_multi_symbol_with_indicator_scoring(candles, lambda symbol, history: Signal())

    assert result.result.metrics.total_trades == 2
    assert len(result.signal_records) == 2
    assert len(result.data_quality_events) == 1
