"""30-day shadow-run validation gate for Phase 7."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from statistics import mean

from .audit_store import InMemoryAuditStore
from .event_bus import RuntimeEventType


class ShadowRunRecommendation(StrEnum):
    CONTINUE_PAPER = "CONTINUE_PAPER"
    CONTINUE_SHADOW = "CONTINUE_SHADOW"
    READY_FOR_MANUAL_REVIEW = "READY_FOR_MANUAL_REVIEW"


@dataclass(frozen=True)
class ShadowRunStatus:
    trading_days_completed: int
    market_sessions_observed: int
    total_signals: int
    total_approvals_requested: int
    total_previews_generated: int
    blocked_orders_count: int
    reconciliation_failures: int
    stale_feed_incidents: int
    data_quality_failures: int
    max_paper_drawdown: float
    daily_pnl_stats: dict[str, float]
    signal_distribution: dict[str, int]
    win_loss_metrics: dict[str, float]
    uptime_percentage: float
    incident_log: tuple[str, ...]
    recommendation: ShadowRunRecommendation
    go_live_allowed: bool = False
    failure_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class ShadowRunGateConfig:
    minimum_trading_days: int = 30
    minimum_sample_count: int = 100
    minimum_connection_uptime_pct: float = 95.0
    max_data_quality_failures: int = 5
    max_drawdown_pct: float = 15.0
    minimum_profit_factor: float = 1.5
    minimum_win_rate: float = 50.0
    max_risk_blocks: int = 50


class ShadowRunValidator:
    """Evaluate a shadow run from audit events; never authorizes LIVE_AUTO."""

    def __init__(self, audit_store: InMemoryAuditStore, config: ShadowRunGateConfig | None = None) -> None:
        self.audit_store = audit_store
        self.config = config or ShadowRunGateConfig()

    def status(self) -> ShadowRunStatus:
        events = self.audit_store.all_events()
        trading_days = {event.timestamp.date().isoformat() for event in events if event.event_type in {RuntimeEventType.TICK_RECEIVED, RuntimeEventType.ZERODHA_TICK_RECEIVED, RuntimeEventType.SIGNAL_GENERATED}}
        signal_events = [event for event in events if event.event_type == RuntimeEventType.SIGNAL_GENERATED]
        risk_events = [event for event in events if event.event_type == RuntimeEventType.RISK_BLOCKED]
        blocked_orders = [event for event in events if event.event_type == RuntimeEventType.REAL_ORDER_BLOCKED]
        recon_failures = [event for event in events if event.event_type == RuntimeEventType.BROKER_RECONCILIATION_FAILED]
        stale_incidents = [event for event in risk_events if any("stale" in str(reason).lower() for reason in event.payload.get("reasons", ())) ]
        data_quality_failures = [event for event in risk_events if any(term in " ".join(str(reason).lower() for reason in event.payload.get("reasons", ())) for term in ("stale", "malformed", "duplicate", "outlier", "timestamp"))]
        pnls = [float(event.payload.get("realized_pnl", 0.0) or 0.0) for event in events if event.event_type == RuntimeEventType.PAPER_PNL_UPDATED]
        daily: dict[str, float] = {}
        for event in events:
            if event.event_type == RuntimeEventType.PAPER_PNL_UPDATED:
                daily[event.timestamp.date().isoformat()] = float(event.payload.get("realized_pnl", 0.0) or 0.0)
        signal_distribution: dict[str, int] = {}
        for event in signal_events:
            signal = str(event.payload.get("signal", "UNKNOWN"))
            signal_distribution[signal] = signal_distribution.get(signal, 0) + 1
        wins = [value for value in pnls if value > 0]
        losses = [value for value in pnls if value < 0]
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        win_rate = (len(wins) / len(pnls) * 100.0) if pnls else 0.0
        profit_factor = (gross_profit / gross_loss) if gross_loss else (float("inf") if gross_profit else 0.0)
        disconnects = len([event for event in events if event.event_type in {RuntimeEventType.ZERODHA_DISCONNECTED, RuntimeEventType.ZERODHA_AUTH_FAILED}])
        connected = len([event for event in events if event.event_type in {RuntimeEventType.ZERODHA_CONNECTED, RuntimeEventType.ZERODHA_TICK_RECEIVED}])
        uptime = (connected / max(connected + disconnects, 1)) * 100.0
        max_drawdown = max([float(event.payload.get("drawdown_pct", 0.0) or 0.0) for event in events if event.event_type == RuntimeEventType.PAPER_PNL_UPDATED] or [0.0])
        incidents = tuple(str(event.payload.get("reasons") or event.payload.get("message") or event.event_type.value) for event in events if event.event_type in {RuntimeEventType.RISK_BLOCKED, RuntimeEventType.BROKER_RECONCILIATION_FAILED, RuntimeEventType.REAL_ORDER_BLOCKED, RuntimeEventType.ZERODHA_AUTH_FAILED})
        failures = self._failures(len(trading_days), len(signal_events), len(blocked_orders), len(recon_failures), uptime, len(data_quality_failures), max_drawdown, profit_factor, win_rate, len(risk_events))
        recommendation = ShadowRunRecommendation.READY_FOR_MANUAL_REVIEW if not failures else (ShadowRunRecommendation.CONTINUE_SHADOW if trading_days else ShadowRunRecommendation.CONTINUE_PAPER)
        return ShadowRunStatus(
            trading_days_completed=len(trading_days),
            market_sessions_observed=len(trading_days),
            total_signals=len(signal_events),
            total_approvals_requested=len([event for event in events if event.event_type == RuntimeEventType.TRADE_APPROVAL_REQUESTED]),
            total_previews_generated=len([event for event in events if event.event_type == RuntimeEventType.ZERODHA_ORDER_PREVIEW_GENERATED]),
            blocked_orders_count=len(blocked_orders),
            reconciliation_failures=len(recon_failures),
            stale_feed_incidents=len(stale_incidents),
            data_quality_failures=len(data_quality_failures),
            max_paper_drawdown=max_drawdown,
            daily_pnl_stats={"days": float(len(daily)), "average": mean(daily.values()) if daily else 0.0, "best": max(daily.values()) if daily else 0.0, "worst": min(daily.values()) if daily else 0.0},
            signal_distribution=signal_distribution,
            win_loss_metrics={"wins": float(len(wins)), "losses": float(len(losses)), "win_rate": win_rate, "profit_factor": profit_factor},
            uptime_percentage=uptime,
            incident_log=incidents,
            recommendation=recommendation,
            go_live_allowed=False,
            failure_reasons=failures,
        )

    def _failures(self, days: int, samples: int, blocked_orders: int, recon_failures: int, uptime: float, data_failures: int, drawdown: float, profit_factor: float, win_rate: float, risk_blocks: int) -> tuple[str, ...]:
        failures: list[str] = []
        if days < self.config.minimum_trading_days:
            failures.append(f"trading days {days} below minimum {self.config.minimum_trading_days}")
        if samples < self.config.minimum_sample_count:
            failures.append(f"sample count {samples} below minimum {self.config.minimum_sample_count}")
        if blocked_orders:
            failures.append("real-order safety violation detected")
        if recon_failures:
            failures.append("unresolved reconciliation drift detected")
        if uptime < self.config.minimum_connection_uptime_pct:
            failures.append(f"uptime {uptime:.2f}% below threshold {self.config.minimum_connection_uptime_pct:.2f}%")
        if data_failures > self.config.max_data_quality_failures:
            failures.append("data quality threshold exceeded")
        if drawdown > self.config.max_drawdown_pct:
            failures.append("paper drawdown threshold exceeded")
        if profit_factor < self.config.minimum_profit_factor:
            failures.append("profit factor threshold not met")
        if win_rate < self.config.minimum_win_rate:
            failures.append("win-rate threshold not met")
        if risk_blocks > self.config.max_risk_blocks:
            failures.append("risk-block sanity threshold exceeded")
        return tuple(failures)
