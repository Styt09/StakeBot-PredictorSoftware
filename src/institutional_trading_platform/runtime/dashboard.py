"""Read-only dashboard summary services for ALPHA-GATE X Phase 7."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..alpha_gate_x import TradingMode
from .audit_store import InMemoryAuditStore
from .event_bus import RuntimeEvent, RuntimeEventType


@dataclass(frozen=True)
class DashboardSummary:
    """Read-only runtime status assembled from the audit/event store."""

    runtime_mode: TradingMode
    zerodha_auth_status: str
    websocket_status: str
    subscribed_symbols: tuple[str, ...]
    last_tick_time: datetime | None
    stale_feed: bool
    candles_finalized: int
    signals_generated: int
    approval_requests: int
    order_previews: int
    blocked_real_orders: int
    reconciliation_status: str
    open_approved_plans: int
    exit_suggestions: int
    realized_paper_pnl: float
    unrealized_paper_pnl: float
    risk_block_reasons: tuple[str, ...]
    kill_switch_active: bool
    go_live_allowed: bool = False


class DashboardSummaryService:
    """Build dashboard data from real runtime events only; no fake values."""

    def __init__(self, audit_store: InMemoryAuditStore, *, runtime_mode: TradingMode = TradingMode.PAPER_TRADING, subscribed_symbols: tuple[str, ...] = ()) -> None:
        self.audit_store = audit_store
        self.runtime_mode = runtime_mode
        self.subscribed_symbols = subscribed_symbols

    def summary(self, now: datetime | None = None, stale_after_seconds: int = 5) -> DashboardSummary:
        now = now or datetime.now(timezone.utc)
        events = self.audit_store.all_events()
        last_tick = self._last_event(events, RuntimeEventType.TICK_RECEIVED) or self._last_event(events, RuntimeEventType.ZERODHA_TICK_RECEIVED)
        last_pnl = self._last_event(events, RuntimeEventType.PAPER_PNL_UPDATED)
        risk_reasons = tuple(str(reason) for event in events if event.event_type == RuntimeEventType.RISK_BLOCKED for reason in event.payload.get("reasons", ()))
        reconciliation = "UNKNOWN"
        if self._last_event(events, RuntimeEventType.BROKER_RECONCILIATION_FAILED) is not None:
            reconciliation = "FAILED"
        if self._last_event(events, RuntimeEventType.BROKER_RECONCILIATION_PASSED) is not None:
            last_pass = self._last_event(events, RuntimeEventType.BROKER_RECONCILIATION_PASSED)
            last_fail = self._last_event(events, RuntimeEventType.BROKER_RECONCILIATION_FAILED)
            reconciliation = "PASSED" if last_fail is None or (last_pass and last_pass.timestamp >= last_fail.timestamp) else "FAILED"
        auth_status = "UNKNOWN"
        if self._last_event(events, RuntimeEventType.ZERODHA_CONNECTED) is not None:
            auth_status = "CONNECTED"
        if self._last_event(events, RuntimeEventType.ZERODHA_AUTH_FAILED) is not None:
            last_auth = self._last_event(events, RuntimeEventType.ZERODHA_AUTH_FAILED)
            last_connected = self._last_event(events, RuntimeEventType.ZERODHA_CONNECTED)
            auth_status = "AUTH_FAILED" if last_connected is None or (last_auth and last_auth.timestamp >= last_connected.timestamp) else "CONNECTED"
        websocket_status = "DISCONNECTED" if self._last_event(events, RuntimeEventType.ZERODHA_DISCONNECTED) else "UNKNOWN"
        if self._last_event(events, RuntimeEventType.ZERODHA_TICK_RECEIVED):
            websocket_status = "CONNECTED"
        stale_feed = bool(risk_reasons and any("stale" in reason.lower() for reason in risk_reasons))
        if last_tick is not None and (now - last_tick.timestamp).total_seconds() > stale_after_seconds:
            stale_feed = True
        return DashboardSummary(
            runtime_mode=self.runtime_mode,
            zerodha_auth_status=auth_status,
            websocket_status=websocket_status,
            subscribed_symbols=self.subscribed_symbols,
            last_tick_time=last_tick.timestamp if last_tick else None,
            stale_feed=stale_feed,
            candles_finalized=len([event for event in events if event.event_type == RuntimeEventType.CANDLE_FINALIZED]),
            signals_generated=len([event for event in events if event.event_type == RuntimeEventType.SIGNAL_GENERATED]),
            approval_requests=len([event for event in events if event.event_type == RuntimeEventType.TRADE_APPROVAL_REQUESTED]),
            order_previews=len([event for event in events if event.event_type == RuntimeEventType.ZERODHA_ORDER_PREVIEW_GENERATED]),
            blocked_real_orders=len([event for event in events if event.event_type == RuntimeEventType.REAL_ORDER_BLOCKED]),
            reconciliation_status=reconciliation,
            open_approved_plans=max(0, len([event for event in events if event.event_type == RuntimeEventType.TRADE_APPROVED]) - len([event for event in events if event.event_type == RuntimeEventType.EXIT_SUGGESTED])),
            exit_suggestions=len([event for event in events if event.event_type == RuntimeEventType.EXIT_SUGGESTED]),
            realized_paper_pnl=float((last_pnl.payload.get("realized_pnl", 0.0) if last_pnl else 0.0) or 0.0),
            unrealized_paper_pnl=float((last_pnl.payload.get("unrealized_pnl", 0.0) if last_pnl else 0.0) or 0.0),
            risk_block_reasons=risk_reasons,
            kill_switch_active=any("kill switch" in reason.lower() for reason in risk_reasons),
            go_live_allowed=False,
        )

    @staticmethod
    def _last_event(events: tuple[RuntimeEvent, ...], event_type: RuntimeEventType) -> RuntimeEvent | None:
        matches = [event for event in events if event.event_type == event_type]
        return matches[-1] if matches else None
