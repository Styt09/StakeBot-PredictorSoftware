"""Final validation report, go-live gate, and exports."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from io import StringIO
from typing import Sequence
from uuid import uuid4

from ..market_data_spine import TradeRecord
from .equity_curve import drawdown_curve
from .performance_metrics import PerformanceMetrics
from .risk_report import RiskReport
from .walk_forward import WalkForwardResult


@dataclass(frozen=True)
class GoLiveGateConfig:
    minimum_trades: int = 100
    minimum_profit_factor: float = 1.5
    maximum_drawdown_pct: float = 15.0
    minimum_win_rate: float = 50.0
    minimum_no_trade_percentage: float = 5.0
    maximum_losing_streak: int = 8


@dataclass(frozen=True)
class GoLiveGateResult:
    verdict: str
    go_live_allowed: bool
    failure_reasons: tuple[str, ...]
    recommendations: tuple[str, ...]


@dataclass(frozen=True)
class ValidationReport:
    run_id: str
    created_at: datetime
    strategy_name: str
    trading_profile: str
    symbols: tuple[str, ...]
    timeframe: str
    start_date: datetime
    end_date: datetime
    initial_capital: float
    metrics: PerformanceMetrics
    equity_curve: tuple[float, ...]
    drawdown_curve: tuple[float, ...]
    walk_forward_results: WalkForwardResult | None
    regime_analysis: object
    symbol_analysis: object
    time_analysis: object
    risk_report: RiskReport
    verdict: str
    go_live_allowed: bool
    failure_reasons: tuple[str, ...]
    recommendations: tuple[str, ...]


def evaluate_go_live_gate(
    metrics: PerformanceMetrics,
    risk_report: RiskReport,
    walk_forward_result: WalkForwardResult | None = None,
    config: GoLiveGateConfig | None = None,
) -> GoLiveGateResult:
    """Apply strict go-live validation criteria."""

    config = config or GoLiveGateConfig()
    failures: list[str] = []
    recommendations: list[str] = []
    if metrics.total_trades < config.minimum_trades:
        failures.append(f"total trades {metrics.total_trades} below minimum {config.minimum_trades}")
        recommendations.append("collect a larger out-of-sample trade sample before go-live")
    if metrics.profit_factor < config.minimum_profit_factor:
        failures.append(f"profit factor {metrics.profit_factor:.2f} below minimum {config.minimum_profit_factor:.2f}")
    if metrics.max_drawdown_percentage > config.maximum_drawdown_pct:
        failures.append(f"max drawdown {metrics.max_drawdown_percentage:.2f}% exceeds maximum {config.maximum_drawdown_pct:.2f}%")
    if metrics.win_rate < config.minimum_win_rate:
        failures.append(f"win rate {metrics.win_rate:.2f}% below minimum {config.minimum_win_rate:.2f}%")
    if metrics.no_trade_percentage < config.minimum_no_trade_percentage:
        failures.append(f"no-trade percentage {metrics.no_trade_percentage:.2f}% suspiciously low")
    if risk_report.bad_data_block_count or risk_report.data_unavailable_count:
        failures.append("critical data-quality errors present")
    if walk_forward_result is not None and walk_forward_result.aggregate_net_profit < 0:
        failures.append("out-of-sample walk-forward net profit is negative")
    if metrics.max_consecutive_losses > config.maximum_losing_streak:
        failures.append(f"largest losing streak {metrics.max_consecutive_losses} exceeds limit {config.maximum_losing_streak}")
    if metrics.expectancy <= 0:
        failures.append(f"expectancy {metrics.expectancy:.2f} is not positive")
    if failures:
        verdict = "NEEDS_MORE_DATA" if metrics.total_trades < config.minimum_trades else "FAIL"
        recommendations.append("keep system in PAPER_TRADING or APPROVAL_MODE; do not enable LIVE_AUTO")
        return GoLiveGateResult(verdict, False, tuple(failures), tuple(recommendations))
    return GoLiveGateResult("PASS", True, (), ("continue staged paper/approval validation before any limited live rollout",))


def create_validation_report(
    *,
    strategy_name: str,
    trading_profile: str,
    symbols: Sequence[str],
    timeframe: str,
    start_date: datetime,
    end_date: datetime,
    initial_capital: float,
    metrics: PerformanceMetrics,
    equity_curve: Sequence[float],
    walk_forward_results: WalkForwardResult | None,
    regime_analysis: object,
    symbol_analysis: object,
    time_analysis: object,
    risk_report: RiskReport,
    gate_config: GoLiveGateConfig | None = None,
) -> ValidationReport:
    """Create final institutional validation report object."""

    gate = evaluate_go_live_gate(metrics, risk_report, walk_forward_results, gate_config)
    return ValidationReport(
        run_id=f"validation-{uuid4()}",
        created_at=datetime.now(timezone.utc),
        strategy_name=strategy_name,
        trading_profile=trading_profile,
        symbols=tuple(symbols),
        timeframe=timeframe,
        start_date=start_date,
        end_date=end_date,
        initial_capital=initial_capital,
        metrics=metrics,
        equity_curve=tuple(equity_curve),
        drawdown_curve=drawdown_curve(equity_curve),
        walk_forward_results=walk_forward_results,
        regime_analysis=regime_analysis,
        symbol_analysis=symbol_analysis,
        time_analysis=time_analysis,
        risk_report=risk_report,
        verdict=gate.verdict,
        go_live_allowed=gate.go_live_allowed,
        failure_reasons=gate.failure_reasons,
        recommendations=gate.recommendations,
    )


def report_to_json(report: ValidationReport) -> str:
    """Export report as JSON."""

    return json.dumps(_jsonable(report), indent=2, sort_keys=True)


def report_to_markdown(report: ValidationReport) -> str:
    """Export report as Markdown."""

    return "\n".join(
        [
            f"# {report.strategy_name} Validation Report",
            "",
            f"Run ID: `{report.run_id}`",
            f"Verdict: **{report.verdict}**",
            f"Go-live allowed: **{report.go_live_allowed}**",
            f"Total trades: {report.metrics.total_trades}",
            f"Win rate: {report.metrics.win_rate:.2f}%",
            f"Profit factor: {report.metrics.profit_factor:.2f}",
            f"Max drawdown: {report.metrics.max_drawdown_percentage:.2f}%",
            "",
            "## Failure reasons",
            *(f"- {reason}" for reason in report.failure_reasons),
            "",
            "## Recommendations",
            *(f"- {item}" for item in report.recommendations),
        ]
    )


def trades_to_csv(trades: Sequence[TradeRecord]) -> str:
    """Export trades as CSV text."""

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["symbol", "side", "entry_time", "exit_time", "entry_price", "exit_price", "quantity", "pnl"])
    for trade in trades:
        writer.writerow([trade.symbol, trade.side.value, trade.entry_time.isoformat(), trade.exit_time.isoformat(), trade.entry_price, trade.exit_price, trade.quantity, trade.pnl])
    return output.getvalue()


def equity_curve_to_csv(equity_curve: Sequence[float]) -> str:
    """Export equity curve as CSV text."""

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["step", "equity"])
    for index, equity in enumerate(equity_curve):
        writer.writerow([index, equity])
    return output.getvalue()


def _jsonable(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "__dataclass_fields__"):
        return {key: _jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value
