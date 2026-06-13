"""Phase 11 strategy robustness and anti-overfitting validation.

The validator is intentionally conservative: missing out-of-sample evidence,
look-ahead/repainting suspicion, or unrealistic execution assumptions block
manual-review readiness instead of fabricating a robustness pass.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from enum import StrEnum
from statistics import mean, pstdev
from typing import Mapping, Sequence

from ..market_data_spine import TradeRecord
from .performance_metrics import calculate_performance_metrics, max_drawdown


class RobustnessRecommendation(StrEnum):
    CONTINUE_VALIDATION = "CONTINUE_VALIDATION"
    REDESIGN_STRATEGY = "REDESIGN_STRATEGY"
    READY_FOR_MANUAL_REVIEW = "READY_FOR_MANUAL_REVIEW"


@dataclass(frozen=True)
class ParameterSensitivityResult:
    parameter_name: str
    tested_values: tuple[float, ...]
    net_profits: tuple[float, ...]
    stability_score: float
    warning: str | None = None


@dataclass(frozen=True)
class RobustnessScorecard:
    overall_score: float
    data_quality_score: float
    sample_size_score: float
    regime_stability_score: float
    symbol_stability_score: float
    timeframe_stability_score: float
    drawdown_quality_score: float
    execution_realism_score: float
    overfitting_risk_score: float
    recommendation: RobustnessRecommendation
    failed_checks: tuple[str, ...]
    warnings: tuple[str, ...]
    critical_flags: tuple[str, ...]
    go_live_allowed: bool = False

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["recommendation"] = self.recommendation.value
        payload["go_live_allowed"] = False
        return payload


@dataclass(frozen=True)
class RobustnessReport:
    scorecard: RobustnessScorecard
    regime_report: dict[str, dict[str, float]]
    symbol_concentration_report: dict[str, object]
    timeframe_report: dict[str, dict[str, float]]
    parameter_sensitivity_report: tuple[ParameterSensitivityResult, ...]
    volatility_bucket_report: dict[str, dict[str, float]]
    trend_range_choppy_report: dict[str, dict[str, float]]
    exclusion_tags: dict[str, tuple[int, ...]]
    overfitting_warnings: tuple[str, ...]
    go_live_allowed: bool = False

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["scorecard"] = self.scorecard.to_dict()
        payload["parameter_sensitivity_report"] = tuple(asdict(item) for item in self.parameter_sensitivity_report)
        payload["go_live_allowed"] = False
        return payload


@dataclass(frozen=True)
class RobustnessValidationInput:
    trades: tuple[TradeRecord, ...]
    equity_curve: tuple[float, ...]
    out_of_sample_trades: tuple[TradeRecord, ...] = ()
    walk_forward_net_profits: tuple[float, ...] = ()
    trade_regimes: dict[int, str] | None = None
    trade_timeframes: dict[int, str] | None = None
    volatility_buckets: dict[int, str] | None = None
    trend_buckets: dict[int, str] | None = None
    parameter_results: dict[str, dict[float, float]] | None = None
    no_trade_percentage: float = 70.0
    slippage_bps: float = 5.0
    brokerage_per_trade: float = 20.0
    lookahead_suspicion: bool = False
    repainting_suspicion: bool = False
    news_gap_trade_indices: tuple[int, ...] = ()
    low_liquidity_trade_indices: tuple[int, ...] = ()
    data_quality_failures: int = 0
    execution_reports: tuple[object, ...] = ()


class StrategyRobustnessValidator:
    """Conservative robustness scorecard for shadow/backtest evidence."""

    def __init__(self, *, min_trades: int = 100, max_profit_concentration_pct: float = 50.0, min_score_for_review: float = 70.0) -> None:
        self.min_trades = min_trades
        self.max_profit_concentration_pct = max_profit_concentration_pct
        self.min_score_for_review = min_score_for_review

    def validate(self, data: RobustnessValidationInput) -> RobustnessReport:
        trades = data.trades
        metrics = calculate_performance_metrics(trades, data.equity_curve, initial_capital=data.equity_curve[0] if data.equity_curve else 100_000.0)
        failures: list[str] = []
        warnings: list[str] = []
        critical: list[str] = []

        if len(trades) < self.min_trades:
            failures.append(f"too few trades: {len(trades)} below minimum {self.min_trades}")
        if not data.out_of_sample_trades:
            failures.append("missing out-of-sample evidence")
        if not data.walk_forward_net_profits:
            failures.append("missing walk-forward evidence")
        elif any(value <= 0 for value in data.walk_forward_net_profits):
            warnings.append("walk-forward fold contains non-positive net profit")

        symbol_report, symbol_concentration = self._concentration(trades, lambda trade: trade.symbol)
        if symbol_concentration > self.max_profit_concentration_pct:
            failures.append("profits concentrated in one symbol")
        day_report, day_concentration = self._concentration(trades, lambda trade: trade.exit_time.date().isoformat())
        if day_concentration > self.max_profit_concentration_pct:
            failures.append("profits concentrated in one day")

        profit_factors = self._bucket_profit_factors(trades, lambda trade: trade.exit_time.date().isoformat())
        if len(profit_factors) >= 2 and _coefficient_of_variation(profit_factors) >= 0.9:
            warnings.append("unstable profit factor across days")
        win_rates = self._bucket_win_rates(trades, lambda trade: trade.exit_time.date().isoformat())
        if len(win_rates) >= 2 and pstdev(win_rates) > 25.0:
            warnings.append("unstable win rate across validation windows")

        if self._expectancy_variance(trades) > max(abs(metrics.expectancy) * 3.0, 1.0):
            warnings.append("high variance expectancy")
        if self._drawdown_clusters(data.equity_curve) > 2:
            warnings.append("excessive drawdown clustering")
        if self._suspiciously_smooth(data.equity_curve, trades):
            warnings.append("suspiciously smooth equity curve")
        if data.no_trade_percentage < 40.0 or data.no_trade_percentage > 95.0:
            warnings.append("unrealistic no-trade percentage")
        if data.slippage_bps <= 0 or data.brokerage_per_trade <= 0:
            critical.append("unrealistic fill assumptions")
        for report in data.execution_reports:
            fill_ratio = float(getattr(report, "fill_ratio", 1.0))
            warnings_for_report = tuple(str(warning).lower() for warning in getattr(report, "warnings", ()))
            quality = float(getattr(report, "execution_quality_score", 100.0))
            if fill_ratio < 0.80:
                warnings.append("low fill ratio execution evidence")
            if any("idealized" in warning for warning in warnings_for_report):
                warnings.append("excessive idealized execution evidence")
            if any("impact" in warning or "liquidity" in warning for warning in warnings_for_report):
                warnings.append("market-impact sensitivity")
            if quality < 50.0:
                critical.append("execution realism failed")
        if data.lookahead_suspicion:
            critical.append("look-ahead-bias suspicion")
        if data.repainting_suspicion:
            critical.append("repainting suspicion")

        regime_report = self._bucket_report(trades, data.trade_regimes or {}, default="UNKNOWN")
        timeframe_report = self._bucket_report(trades, data.trade_timeframes or {}, default="UNKNOWN")
        volatility_report = self._bucket_report(trades, data.volatility_buckets or {}, default="UNKNOWN")
        trend_report = self._bucket_report(trades, data.trend_buckets or {}, default="UNKNOWN")
        sensitivity = self._parameter_sensitivity(data.parameter_results or {})
        for item in sensitivity:
            if item.warning:
                warnings.append(item.warning)

        sample_size_score = min(len(trades) / self.min_trades * 100.0, 100.0) if self.min_trades else 100.0
        data_quality_score = max(0.0, 100.0 - data.data_quality_failures * 10.0 - len(data.news_gap_trade_indices) * 2.0 - len(data.low_liquidity_trade_indices) * 2.0)
        regime_score = self._stability_score(regime_report)
        symbol_score = max(0.0, 100.0 - max(0.0, symbol_concentration - self.max_profit_concentration_pct) * 2.0)
        timeframe_score = self._stability_score(timeframe_report)
        drawdown_score = max(0.0, 100.0 - max_drawdown(data.equity_curve)[1] * 4.0 - self._drawdown_clusters(data.equity_curve) * 10.0)
        execution_score = 100.0 if data.slippage_bps > 0 and data.brokerage_per_trade > 0 else 0.0
        overfit_score = max(0.0, 100.0 - len(failures) * 12.0 - len(warnings) * 7.0 - len(critical) * 30.0)
        overall = mean((data_quality_score, sample_size_score, regime_score, symbol_score, timeframe_score, drawdown_score, execution_score, overfit_score))

        if critical or data.lookahead_suspicion or data.repainting_suspicion:
            recommendation = RobustnessRecommendation.REDESIGN_STRATEGY
        elif overall >= self.min_score_for_review and not failures:
            recommendation = RobustnessRecommendation.READY_FOR_MANUAL_REVIEW
        else:
            recommendation = RobustnessRecommendation.CONTINUE_VALIDATION

        scorecard = RobustnessScorecard(
            overall_score=round(overall, 2),
            data_quality_score=round(data_quality_score, 2),
            sample_size_score=round(sample_size_score, 2),
            regime_stability_score=round(regime_score, 2),
            symbol_stability_score=round(symbol_score, 2),
            timeframe_stability_score=round(timeframe_score, 2),
            drawdown_quality_score=round(drawdown_score, 2),
            execution_realism_score=round(execution_score, 2),
            overfitting_risk_score=round(overfit_score, 2),
            recommendation=recommendation,
            failed_checks=tuple(failures),
            warnings=tuple(warnings),
            critical_flags=tuple(critical),
            go_live_allowed=False,
        )
        return RobustnessReport(
            scorecard=scorecard,
            regime_report=regime_report,
            symbol_concentration_report={"by_symbol": symbol_report, "max_profit_concentration_pct": round(symbol_concentration, 2), "by_day": day_report, "max_day_concentration_pct": round(day_concentration, 2)},
            timeframe_report=timeframe_report,
            parameter_sensitivity_report=sensitivity,
            volatility_bucket_report=volatility_report,
            trend_range_choppy_report=trend_report,
            exclusion_tags={"news_gap_trade_indices": data.news_gap_trade_indices, "low_liquidity_trade_indices": data.low_liquidity_trade_indices},
            overfitting_warnings=tuple(warnings + critical),
            go_live_allowed=False,
        )

    def _concentration(self, trades: Sequence[TradeRecord], key_fn) -> tuple[dict[str, float], float]:
        profits: dict[str, float] = defaultdict(float)
        total_positive = sum(max(trade.pnl, 0.0) for trade in trades)
        for trade in trades:
            profits[str(key_fn(trade))] += max(trade.pnl, 0.0)
        report = {key: round(value, 2) for key, value in profits.items()}
        concentration = (max(profits.values()) / total_positive * 100.0) if profits and total_positive > 0 else 0.0
        return report, concentration

    def _bucket_report(self, trades: Sequence[TradeRecord], labels: Mapping[int, str], *, default: str) -> dict[str, dict[str, float]]:
        buckets: dict[str, list[TradeRecord]] = defaultdict(list)
        for index, trade in enumerate(trades):
            buckets[labels.get(index, default)].append(trade)
        return {name: self._summary(tuple(items)) for name, items in sorted(buckets.items())}

    def _summary(self, trades: Sequence[TradeRecord]) -> dict[str, float]:
        if not trades:
            return {"trades": 0.0, "net_pnl": 0.0, "win_rate": 0.0, "profit_factor": 0.0}
        equity = [100_000.0]
        for trade in trades:
            equity.append(equity[-1] + trade.pnl)
        metrics = calculate_performance_metrics(trades, tuple(equity), initial_capital=100_000.0)
        return {"trades": float(metrics.total_trades), "net_pnl": round(metrics.net_profit, 2), "win_rate": round(metrics.win_rate, 2), "profit_factor": round(metrics.profit_factor, 2) if metrics.profit_factor != float("inf") else 999.0}

    def _bucket_profit_factors(self, trades: Sequence[TradeRecord], key_fn) -> list[float]:
        buckets: dict[str, list[TradeRecord]] = defaultdict(list)
        for trade in trades:
            buckets[str(key_fn(trade))].append(trade)
        return [min(self._summary(tuple(items))["profit_factor"], 999.0) for items in buckets.values()]

    def _bucket_win_rates(self, trades: Sequence[TradeRecord], key_fn) -> list[float]:
        buckets: dict[str, list[TradeRecord]] = defaultdict(list)
        for trade in trades:
            buckets[str(key_fn(trade))].append(trade)
        return [self._summary(tuple(items))["win_rate"] for items in buckets.values()]

    def _parameter_sensitivity(self, parameter_results: Mapping[str, Mapping[float, float]]) -> tuple[ParameterSensitivityResult, ...]:
        results = []
        for name, values in parameter_results.items():
            ordered = tuple(sorted(values.items()))
            tested = tuple(key for key, _ in ordered)
            profits = tuple(value for _, value in ordered)
            score = 100.0 if len(profits) <= 1 else max(0.0, 100.0 - _coefficient_of_variation([abs(value) for value in profits]) * 50.0)
            warning = f"parameter {name} sensitivity unstable" if score < 50.0 else None
            results.append(ParameterSensitivityResult(name, tested, profits, round(score, 2), warning))
        return tuple(results)

    def _stability_score(self, report: Mapping[str, Mapping[str, float]]) -> float:
        active = [item for item in report.values() if item.get("trades", 0.0) > 0]
        if not active:
            return 0.0
        if len(active) == 1:
            return 60.0
        pnls = [item.get("net_pnl", 0.0) for item in active]
        negative_penalty = len([pnl for pnl in pnls if pnl < 0]) * 15.0
        return max(0.0, min(100.0, 100.0 - _coefficient_of_variation([abs(pnl) for pnl in pnls]) * 25.0 - negative_penalty))

    def _expectancy_variance(self, trades: Sequence[TradeRecord]) -> float:
        return pstdev([trade.pnl for trade in trades]) if len(trades) >= 2 else 0.0

    def _drawdown_clusters(self, equity_curve: Sequence[float]) -> int:
        clusters = 0
        in_cluster = False
        peak = equity_curve[0] if equity_curve else 0.0
        for equity in equity_curve:
            peak = max(peak, equity)
            drawdown_pct = ((peak - equity) / peak * 100.0) if peak else 0.0
            if drawdown_pct > 5.0 and not in_cluster:
                clusters += 1
                in_cluster = True
            if drawdown_pct == 0.0:
                in_cluster = False
        return clusters

    def _suspiciously_smooth(self, equity_curve: Sequence[float], trades: Sequence[TradeRecord]) -> bool:
        if len(trades) < max(self.min_trades, 20):
            return False
        pnls = [trade.pnl for trade in trades]
        return all(pnl >= 0 for pnl in pnls) and max_drawdown(equity_curve)[1] == 0.0


def _coefficient_of_variation(values: Sequence[float]) -> float:
    cleaned = [abs(value) for value in values if value is not None]
    if len(cleaned) < 2:
        return 0.0
    avg = mean(cleaned)
    return (pstdev(cleaned) / avg) if avg else 0.0
