"""Daily shadow-run report generation for Phase 10."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date

from .audit_store import InMemoryAuditStore
from .event_bus import RuntimeEvent, RuntimeEventType
from .shadow_run import ShadowRunRecommendation


@dataclass(frozen=True)
class DailyShadowReport:
    trading_day: date
    symbols_observed: tuple[str, ...]
    session_uptime: float
    ticks_received: int
    candles_finalized: int
    signals_generated: int
    approvals_requested: int
    previews_generated: int
    blocked_order_attempts: int
    reconciliation_failures: int
    stale_feed_incidents: int
    data_quality_failures: int
    paper_pnl: float
    drawdown: float
    alerts: tuple[dict[str, object], ...]
    incidents: tuple[str, ...]
    recommendation: ShadowRunRecommendation
    go_live_allowed: bool = False

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["trading_day"] = self.trading_day.isoformat()
        payload["recommendation"] = self.recommendation.value
        return payload


class DailyShadowReportGenerator:
    """Generate daily reports from persisted/audited runtime events only."""

    def __init__(self, audit_store: InMemoryAuditStore) -> None:
        self.audit_store = audit_store

    def generate(self, trading_day: date) -> DailyShadowReport:
        events = tuple(event for event in self.audit_store.all_events() if event.timestamp.date() == trading_day)
        symbols = tuple(sorted({event.symbol for event in events if event.symbol}))
        ticks = self._events(events, RuntimeEventType.TICK_RECEIVED) + self._events(events, RuntimeEventType.ZERODHA_TICK_RECEIVED)
        disconnects = len(self._events(events, RuntimeEventType.ZERODHA_DISCONNECTED) + self._events(events, RuntimeEventType.ZERODHA_AUTH_FAILED))
        uptime = (len(ticks) / max(len(ticks) + disconnects, 1)) * 100.0
        risk_events = self._events(events, RuntimeEventType.RISK_BLOCKED)
        stale = [event for event in risk_events if any("stale" in str(reason).lower() for reason in event.payload.get("reasons", ()))]
        data_quality = [event for event in risk_events if any(term in " ".join(str(reason).lower() for reason in event.payload.get("reasons", ())) for term in ("stale", "malformed", "duplicate", "outlier", "timestamp"))]
        pnl_events = self._events(events, RuntimeEventType.PAPER_PNL_UPDATED)
        latest_pnl = pnl_events[-1].payload if pnl_events else {}
        incidents = tuple(str(event.payload.get("reasons") or event.payload.get("reason") or event.event_type.value) for event in events if event.event_type in {RuntimeEventType.RISK_BLOCKED, RuntimeEventType.BROKER_RECONCILIATION_FAILED, RuntimeEventType.REAL_ORDER_BLOCKED, RuntimeEventType.ZERODHA_AUTH_FAILED})
        blocked = len(self._events(events, RuntimeEventType.REAL_ORDER_BLOCKED))
        recon_failures = len(self._events(events, RuntimeEventType.BROKER_RECONCILIATION_FAILED))
        recommendation = ShadowRunRecommendation.CONTINUE_SHADOW if events else ShadowRunRecommendation.CONTINUE_PAPER
        if blocked or recon_failures or data_quality:
            recommendation = ShadowRunRecommendation.CONTINUE_SHADOW
        return DailyShadowReport(
            trading_day=trading_day,
            symbols_observed=symbols,
            session_uptime=uptime,
            ticks_received=len(ticks),
            candles_finalized=len(self._events(events, RuntimeEventType.CANDLE_FINALIZED)),
            signals_generated=len(self._events(events, RuntimeEventType.SIGNAL_GENERATED)),
            approvals_requested=len(self._events(events, RuntimeEventType.TRADE_APPROVAL_REQUESTED)),
            previews_generated=len(self._events(events, RuntimeEventType.ZERODHA_ORDER_PREVIEW_GENERATED)),
            blocked_order_attempts=blocked,
            reconciliation_failures=recon_failures,
            stale_feed_incidents=len(stale),
            data_quality_failures=len(data_quality),
            paper_pnl=float(latest_pnl.get("realized_pnl", 0.0) or 0.0),
            drawdown=float(latest_pnl.get("drawdown_pct", 0.0) or 0.0),
            alerts=tuple(event.payload for event in self._events(events, RuntimeEventType.ALERT_EMITTED)),
            incidents=incidents,
            recommendation=recommendation,
            go_live_allowed=False,
        )

    @staticmethod
    def _events(events: tuple[RuntimeEvent, ...], event_type: RuntimeEventType) -> tuple[RuntimeEvent, ...]:
        return tuple(event for event in events if event.event_type == event_type)
