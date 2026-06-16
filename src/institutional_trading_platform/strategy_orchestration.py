"""Phase 13 multi-strategy orchestration and capital allocation.

The layer coordinates strategy metadata, health scoring, capital allocation,
correlation/overlap diagnostics, and unified signal decisions. It is read-only
with respect to broker execution and always keeps go-live disabled.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from enum import StrEnum
from statistics import fmean, pstdev
from typing import Mapping, Sequence

from .alpha_gate_x import AlphaSignal
from .market_data_spine import TradeRecord
from .validation.equity_curve import build_equity_curve
from .validation.performance_metrics import calculate_performance_metrics


class StrategyRegime(StrEnum):
    TRENDING = "TRENDING"
    RANGING = "RANGING"
    CHOPPY = "CHOPPY"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_VOLATILITY = "LOW_VOLATILITY"


class StrategyRiskProfile(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class StrategyHealthStatus(StrEnum):
    HEALTHY = "HEALTHY"
    WATCHLIST = "WATCHLIST"
    DEGRADED = "DEGRADED"
    DISABLED = "DISABLED"


class AllocationMethod(StrEnum):
    EQUAL_WEIGHT = "EQUAL_WEIGHT"
    PERFORMANCE_WEIGHT = "PERFORMANCE_WEIGHT"
    ROBUSTNESS_WEIGHT = "ROBUSTNESS_WEIGHT"
    VOLATILITY_ADJUSTED = "VOLATILITY_ADJUSTED"
    BLENDED = "BLENDED"


@dataclass(frozen=True)
class StrategyMetadata:
    strategy_id: str
    strategy_name: str
    version: str
    description: str
    supported_symbols: tuple[str, ...]
    supported_timeframes: tuple[str, ...]
    supported_regimes: tuple[StrategyRegime, ...]
    risk_profile: StrategyRiskProfile
    expected_holding_period: str
    enabled_flag: bool = True


class StrategyRegistry:
    """Register and discover strategy engines by metadata."""

    def __init__(self) -> None:
        self._strategies: dict[str, StrategyMetadata] = {}

    def register(self, metadata: StrategyMetadata) -> None:
        if metadata.strategy_id in self._strategies:
            raise ValueError(f"strategy already registered: {metadata.strategy_id}")
        if not metadata.strategy_id.strip() or not metadata.strategy_name.strip():
            raise ValueError("strategy id and name are required")
        self._strategies[metadata.strategy_id] = metadata

    def get(self, strategy_id: str) -> StrategyMetadata:
        return self._strategies[strategy_id]

    def all(self) -> tuple[StrategyMetadata, ...]:
        return tuple(self._strategies.values())

    @classmethod
    def with_defaults(cls) -> "StrategyRegistry":
        registry = cls()
        registry.register(StrategyMetadata("ALPHA_GATE_X", "ALPHA-GATE X", "1.0", "Core high-filter signal engine", ("RELIANCE", "TCS", "INFY"), ("1m", "5m", "15m", "1H", "Daily"), (StrategyRegime.TRENDING, StrategyRegime.RANGING, StrategyRegime.LOW_VOLATILITY), StrategyRiskProfile.MEDIUM, "intraday/swing"))
        registry.register(StrategyMetadata("MOMENTUM", "Momentum", "0.1", "Momentum placeholder strategy contract", ("NSE_EQ",), ("5m", "15m"), (StrategyRegime.TRENDING, StrategyRegime.HIGH_VOLATILITY), StrategyRiskProfile.MEDIUM, "intraday"))
        registry.register(StrategyMetadata("MEAN_REVERSION", "Mean Reversion", "0.1", "Mean reversion placeholder strategy contract", ("NSE_EQ",), ("5m", "15m"), (StrategyRegime.RANGING, StrategyRegime.LOW_VOLATILITY), StrategyRiskProfile.LOW, "intraday"))
        registry.register(StrategyMetadata("BREAKOUT", "Breakout", "0.1", "Breakout placeholder strategy contract", ("NSE_EQ",), ("5m", "15m"), (StrategyRegime.TRENDING, StrategyRegime.HIGH_VOLATILITY), StrategyRiskProfile.HIGH, "intraday"))
        registry.register(StrategyMetadata("VOLATILITY_EXPANSION", "Volatility Expansion", "0.1", "Volatility expansion placeholder strategy contract", ("NSE_EQ",), ("15m", "1H"), (StrategyRegime.HIGH_VOLATILITY,), StrategyRiskProfile.HIGH, "intraday/swing"))
        registry.register(StrategyMetadata("MARKET_BREADTH", "Market Breadth", "0.1", "Market breadth confirmation strategy contract", ("INDEX", "NSE_EQ"), ("15m", "Daily"), (StrategyRegime.TRENDING, StrategyRegime.RANGING), StrategyRiskProfile.LOW, "swing"))
        return registry


@dataclass(frozen=True)
class StrategyPerformanceSnapshot:
    strategy_id: str
    window: str
    trades: int
    win_rate: float
    profit_factor: float
    expectancy: float
    sharpe: float
    sortino: float
    max_drawdown: float
    average_holding_period: float
    realized_pnl: float
    volatility: float
    robustness_score: float


@dataclass(frozen=True)
class StrategyPerformanceHistory:
    strategy_id: str
    current: StrategyPerformanceSnapshot
    rolling_20: StrategyPerformanceSnapshot
    rolling_50: StrategyPerformanceSnapshot
    rolling_100: StrategyPerformanceSnapshot
    degradation_detected: bool
    historical: tuple[StrategyPerformanceSnapshot, ...]


class StrategyPerformanceTracker:
    """Compute strategy-level performance and rolling degradation signals."""

    def __init__(self, initial_capital: float = 100_000.0) -> None:
        self.initial_capital = initial_capital

    def track(self, strategy_id: str, trades: Sequence[TradeRecord], robustness_score: float = 0.0) -> StrategyPerformanceHistory:
        ordered = tuple(trades)
        current = self._snapshot(strategy_id, "ALL", ordered, robustness_score)
        rolling_20 = self._snapshot(strategy_id, "20", ordered[-20:], robustness_score)
        rolling_50 = self._snapshot(strategy_id, "50", ordered[-50:], robustness_score)
        rolling_100 = self._snapshot(strategy_id, "100", ordered[-100:], robustness_score)
        degradation = bool(rolling_20.trades >= 5 and current.trades >= 20 and (rolling_20.expectancy < 0 or rolling_20.win_rate + 15 < current.win_rate or rolling_20.profit_factor < max(current.profit_factor * 0.5, 0.8)))
        return StrategyPerformanceHistory(strategy_id, current, rolling_20, rolling_50, rolling_100, degradation, (current, rolling_20, rolling_50, rolling_100))

    def _snapshot(self, strategy_id: str, window: str, trades: Sequence[TradeRecord], robustness_score: float) -> StrategyPerformanceSnapshot:
        equity = build_equity_curve(self.initial_capital, trades)
        metrics = calculate_performance_metrics(trades, equity, initial_capital=self.initial_capital)
        pnls = [trade.pnl for trade in trades]
        volatility = pstdev(pnls) if len(pnls) >= 2 else 0.0
        return StrategyPerformanceSnapshot(strategy_id, window, metrics.total_trades, metrics.win_rate, metrics.profit_factor if metrics.profit_factor != float("inf") else 999.0, metrics.expectancy, metrics.sharpe_ratio, metrics.sortino_ratio, metrics.max_drawdown_percentage, metrics.average_holding_period, metrics.net_profit, volatility, robustness_score)


@dataclass(frozen=True)
class StrategyHealthScore:
    strategy_id: str
    performance_score: float
    robustness_score: float
    stability_score: float
    drawdown_score: float
    execution_score: float
    overall_score: float
    status: StrategyHealthStatus
    reasons: tuple[str, ...]


class StrategyHealthScorer:
    def score(self, metadata: StrategyMetadata, performance: StrategyPerformanceHistory, execution_score: float = 100.0) -> StrategyHealthScore:
        if not metadata.enabled_flag:
            return StrategyHealthScore(metadata.strategy_id, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, StrategyHealthStatus.DISABLED, ("strategy disabled",))
        current = performance.current
        perf = min(max((current.profit_factor / 2.0) * 50.0 + current.win_rate * 0.5, 0.0), 100.0)
        robustness = min(max(current.robustness_score, 0.0), 100.0)
        stability = 35.0 if performance.degradation_detected else max(0.0, 100.0 - min(current.volatility, 100.0))
        drawdown = max(0.0, 100.0 - current.max_drawdown * 4.0)
        execution = min(max(execution_score, 0.0), 100.0)
        overall = fmean((perf, robustness, stability, drawdown, execution))
        reasons: list[str] = []
        if performance.degradation_detected:
            reasons.append("performance degradation detected")
        if current.max_drawdown > 15:
            reasons.append("drawdown above threshold")
        if robustness < 50:
            reasons.append("robustness below threshold")
        if overall >= 75 and not reasons:
            status = StrategyHealthStatus.HEALTHY
        elif overall >= 60:
            status = StrategyHealthStatus.WATCHLIST
        elif overall >= 35:
            status = StrategyHealthStatus.DEGRADED
        else:
            status = StrategyHealthStatus.DISABLED
        return StrategyHealthScore(metadata.strategy_id, round(perf, 2), round(robustness, 2), round(stability, 2), round(drawdown, 2), round(execution, 2), round(overall, 2), status, tuple(reasons))


@dataclass(frozen=True)
class StrategyRegimeCompatibility:
    strategy_id: str
    regime: StrategyRegime
    score: float
    reason: str


def regime_compatibility(metadata: StrategyMetadata, regime: StrategyRegime) -> StrategyRegimeCompatibility:
    if regime in metadata.supported_regimes:
        return StrategyRegimeCompatibility(metadata.strategy_id, regime, 1.0, "preferred regime")
    weak_pairs = {
        StrategyRegime.TRENDING: {StrategyRegime.CHOPPY},
        StrategyRegime.RANGING: {StrategyRegime.TRENDING},
        StrategyRegime.HIGH_VOLATILITY: {StrategyRegime.LOW_VOLATILITY},
    }
    if any(regime in weak_pairs.get(supported, set()) for supported in metadata.supported_regimes):
        return StrategyRegimeCompatibility(metadata.strategy_id, regime, 0.35, "weak regime fit")
    return StrategyRegimeCompatibility(metadata.strategy_id, regime, 0.0, "unsupported regime")


@dataclass(frozen=True)
class StrategyAllocationReport:
    method: AllocationMethod
    allocations: dict[str, float]
    rejected_strategies: dict[str, tuple[str, ...]]
    min_allocation: float
    max_allocation: float
    go_live_allowed: bool = False


class CapitalAllocationEngine:
    """Allocate shadow capital across strategy health/performance profiles."""

    def __init__(self, min_allocation: float = 0.0, max_allocation: float = 0.50) -> None:
        if min_allocation < 0 or max_allocation <= 0 or min_allocation > max_allocation:
            raise ValueError("allocation caps are invalid")
        self.min_allocation = min_allocation
        self.max_allocation = max_allocation

    def allocate(self, performances: Mapping[str, StrategyPerformanceHistory], health_scores: Mapping[str, StrategyHealthScore], *, method: AllocationMethod = AllocationMethod.BLENDED) -> StrategyAllocationReport:
        raw: dict[str, float] = {}
        rejected: dict[str, tuple[str, ...]] = {}
        for strategy_id, health in health_scores.items():
            perf = performances[strategy_id].current
            if health.status == StrategyHealthStatus.DISABLED:
                raw[strategy_id] = 0.0
                rejected[strategy_id] = ("disabled strategy allocation forced to zero",)
                continue
            if method == AllocationMethod.EQUAL_WEIGHT:
                score = 1.0
            elif method == AllocationMethod.PERFORMANCE_WEIGHT:
                score = max(perf.expectancy, 0.0) + max(perf.profit_factor, 0.0)
            elif method == AllocationMethod.ROBUSTNESS_WEIGHT:
                score = health.robustness_score
            elif method == AllocationMethod.VOLATILITY_ADJUSTED:
                score = health.overall_score / max(perf.volatility, 1.0)
            else:
                score = (health.overall_score * 0.4) + (health.robustness_score * 0.3) + (max(perf.profit_factor, 0.0) * 10.0) + (max(perf.expectancy, 0.0) * 0.1)
            raw[strategy_id] = max(score, 0.0)
        allocations = _normalize_with_caps(raw, self.min_allocation, self.max_allocation)
        return StrategyAllocationReport(method, allocations, rejected, self.min_allocation, self.max_allocation, False)


@dataclass(frozen=True)
class StrategyCorrelationReport:
    pnl_correlation_matrix: dict[str, dict[str, float]]
    signal_correlation_matrix: dict[str, dict[str, float]]
    trade_overlap: dict[str, float]
    overlap_warnings: tuple[str, ...]
    go_live_allowed: bool = False


class StrategyCorrelationAnalyzer:
    def analyze(self, pnl_series_by_strategy: Mapping[str, Sequence[float]], signals_by_strategy: Mapping[str, Sequence[AlphaSignal]] | None = None, trade_times_by_strategy: Mapping[str, Sequence[object]] | None = None, threshold: float = 0.80) -> StrategyCorrelationReport:
        strategies = sorted(pnl_series_by_strategy)
        pnl_matrix = {left: {right: _corr(pnl_series_by_strategy[left], pnl_series_by_strategy[right]) for right in strategies} for left in strategies}
        signals_by_strategy = signals_by_strategy or {}
        signal_numeric = {key: tuple(_signal_value(signal) for signal in values) for key, values in signals_by_strategy.items()}
        signal_matrix = {left: {right: _corr(signal_numeric.get(left, ()), signal_numeric.get(right, ())) for right in strategies} for left in strategies}
        trade_times_by_strategy = trade_times_by_strategy or {}
        overlaps: dict[str, float] = {}
        warnings: list[str] = []
        for i, left in enumerate(strategies):
            for right in strategies[i + 1:]:
                key = f"{left}/{right}"
                overlap = _overlap_ratio(trade_times_by_strategy.get(left, ()), trade_times_by_strategy.get(right, ()))
                overlaps[key] = overlap
                if pnl_matrix[left][right] >= threshold or signal_matrix[left][right] >= threshold or overlap >= threshold:
                    warnings.append(f"excessive similarity detected: {key}")
        return StrategyCorrelationReport(pnl_matrix, signal_matrix, overlaps, tuple(warnings), False)


@dataclass(frozen=True)
class StrategySignal:
    strategy_id: str
    symbol: str
    signal: AlphaSignal
    confidence: float
    robustness_score: float = 0.0


@dataclass(frozen=True)
class ConflictResolutionReport:
    symbol: str
    buy_weight: float
    sell_weight: float
    hold_weight: float
    conflict_score: float
    confidence_reduction: float
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class UnifiedSignalDecision:
    symbol: str
    signal: AlphaSignal
    confidence: float
    weighted_score: float
    contributing_strategies: tuple[str, ...]
    conflict_report: ConflictResolutionReport
    go_live_allowed: bool = False


class UnifiedSignalAggregator:
    def aggregate(self, signals: Sequence[StrategySignal], allocations: Mapping[str, float], health_scores: Mapping[str, StrategyHealthScore]) -> UnifiedSignalDecision:
        if not signals:
            report = ConflictResolutionReport("", 0.0, 0.0, 0.0, 0.0, 0.0, ("no strategy signals",))
            return UnifiedSignalDecision("", AlphaSignal.NO_TRADE, 0.0, 0.0, (), report, False)
        symbol = signals[0].symbol
        weights = {AlphaSignal.BUY: 0.0, AlphaSignal.SELL: 0.0, AlphaSignal.HOLD: 0.0, AlphaSignal.NO_TRADE: 0.0}
        contributors = []
        for signal in signals:
            health = health_scores.get(signal.strategy_id)
            if health is None or health.status == StrategyHealthStatus.DISABLED:
                continue
            weight = allocations.get(signal.strategy_id, 0.0) * signal.confidence * (health.overall_score / 100.0) * max(signal.robustness_score, health.robustness_score) / 100.0
            weights[signal.signal] += weight
            contributors.append(signal.strategy_id)
        buy = weights[AlphaSignal.BUY]
        sell = weights[AlphaSignal.SELL]
        hold = weights[AlphaSignal.HOLD] + weights[AlphaSignal.NO_TRADE]
        conflict = min(buy, sell) / max(buy + sell, 1e-9)
        reduction = min(conflict * 0.5, 0.5)
        if max(buy, sell, hold) == hold:
            decision = AlphaSignal.HOLD
            score = 0.0
        elif buy > sell:
            decision = AlphaSignal.BUY
            score = buy - sell
        elif sell > buy:
            decision = AlphaSignal.SELL
            score = sell - buy
        else:
            decision = AlphaSignal.NO_TRADE
            score = 0.0
        confidence = max(0.0, min(1.0, score * (1.0 - reduction)))
        reasons = ("opposing BUY/SELL strategies reduced confidence",) if conflict > 0 else ()
        report = ConflictResolutionReport(symbol, buy, sell, hold, round(conflict, 4), round(reduction, 4), reasons)
        return UnifiedSignalDecision(symbol, decision, round(confidence, 4), round(score, 4), tuple(contributors), report, False)


def multi_strategy_evidence_section(
    registry: StrategyRegistry,
    health_scores: Mapping[str, StrategyHealthScore],
    allocation_report: StrategyAllocationReport,
    correlation_report: StrategyCorrelationReport,
    regime_scores: Sequence[StrategyRegimeCompatibility],
    unified_decisions: Sequence[UnifiedSignalDecision],
) -> dict[str, object]:
    """Build evidence-pack-ready multi-strategy diagnostics."""

    return {
        "registered_strategies": tuple(asdict(strategy) for strategy in registry.all()),
        "health_scores": {key: asdict(value) for key, value in health_scores.items()},
        "allocations": asdict(allocation_report),
        "correlation_matrix": correlation_report.pnl_correlation_matrix,
        "overlap_warnings": correlation_report.overlap_warnings,
        "regime_compatibility": tuple(asdict(score) for score in regime_scores),
        "unified_decisions": tuple(asdict(decision) for decision in unified_decisions),
        "conflict_reports": tuple(asdict(decision.conflict_report) for decision in unified_decisions),
        "go_live_allowed": False,
    }


def _normalize_with_caps(raw: Mapping[str, float], minimum: float, maximum: float) -> dict[str, float]:
    positive = {key: value for key, value in raw.items() if value > 0}
    if not positive:
        return {key: 0.0 for key in raw}
    total = sum(positive.values())
    normalized = {key: value / total for key, value in positive.items()}
    capped = {key: min(max(value, minimum), maximum) for key, value in normalized.items()}
    for key in raw:
        capped.setdefault(key, 0.0)
    total_capped = sum(capped.values())
    if total_capped > 1.0:
        return {key: value / total_capped for key, value in capped.items()}
    return capped


def _corr(left: Sequence[float], right: Sequence[float]) -> float:
    length = min(len(left), len(right))
    if length < 2:
        return 0.0
    a = tuple(float(value) for value in left[:length])
    b = tuple(float(value) for value in right[:length])
    mean_a = fmean(a)
    mean_b = fmean(b)
    cov = sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b, strict=True))
    var_a = sum((x - mean_a) ** 2 for x in a)
    var_b = sum((y - mean_b) ** 2 for y in b)
    if var_a == 0 or var_b == 0:
        return 0.0
    return cov / (var_a * var_b) ** 0.5


def _signal_value(signal: AlphaSignal) -> float:
    return {AlphaSignal.BUY: 1.0, AlphaSignal.SELL: -1.0, AlphaSignal.HOLD: 0.0, AlphaSignal.NO_TRADE: 0.0}[signal]


def _overlap_ratio(left: Sequence[object], right: Sequence[object]) -> float:
    if not left or not right:
        return 0.0
    left_set = set(left)
    right_set = set(right)
    return len(left_set & right_set) / max(len(left_set | right_set), 1)
