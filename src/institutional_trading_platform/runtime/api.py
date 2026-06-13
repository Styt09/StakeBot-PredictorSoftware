"""Read-only API facade for Phase 7 dashboard endpoints."""

from __future__ import annotations

from dataclasses import asdict

from .audit_store import InMemoryAuditStore
from .dashboard import DashboardSummaryService
from .event_bus import RuntimeEventType
from .live_paper_engine import LivePaperTradingEngine
from .persistence import SQLiteAuditStore
from .recovery import CrashRecoveryService
from .shadow_run import ShadowRunValidator
from .daily_report import DailyShadowReportGenerator
from .evidence_pack import EvidencePackGenerator
from .manual_review import ManualReviewGate
from ..strategy_orchestration import CapitalAllocationEngine, StrategyCorrelationAnalyzer, StrategyRegistry, UnifiedSignalAggregator


class ReadOnlyRuntimeAPI:
    """Function-based read-only API facade; no method places orders."""

    def __init__(self, audit_store: InMemoryAuditStore | SQLiteAuditStore, dashboard: DashboardSummaryService, shadow: ShadowRunValidator, engine: LivePaperTradingEngine | None = None, recovery: CrashRecoveryService | None = None, orchestrator: object | None = None, strategy_context: dict[str, object] | None = None) -> None:
        self.audit_store = audit_store
        self.dashboard = dashboard
        self.shadow = shadow
        self.engine = engine
        self.recovery = recovery
        self.orchestrator = orchestrator
        self.strategy_context = strategy_context or {}

    def health(self) -> dict[str, object]:
        return {"status": "ok", "read_only": True, "go_live_allowed": False}

    def runtime_status(self) -> dict[str, object]:
        return asdict(self.dashboard.summary())

    def runtime_events(self) -> tuple[object, ...]:
        return self.audit_store.all_events()

    def latest_persisted_events(self, limit: int = 100) -> tuple[object, ...]:
        if hasattr(self.audit_store, "latest_events"):
            return self.audit_store.latest_events(limit)
        return self.audit_store.all_events()[-limit:]

    def event_lookup(self, event_id: str) -> object | None:
        if hasattr(self.audit_store, "by_event_id"):
            return self.audit_store.by_event_id(event_id)
        return next((event for event in self.audit_store.all_events() if event.event_id == event_id), None)

    def runtime_events_by_correlation(self, correlation_id: str) -> tuple[object, ...]:
        return self.audit_store.by_correlation_id(correlation_id)

    def runtime_symbols(self, symbol: str) -> tuple[object, ...]:
        return self.audit_store.by_symbol(symbol)

    def runtime_report(self) -> dict[str, object]:
        if self.engine is None:
            return {"available": False, "go_live_allowed": False}
        return asdict(self.engine.build_report())

    def approvals_pending(self) -> tuple[object, ...]:
        return self.audit_store.by_event_type(RuntimeEventType.TRADE_APPROVAL_REQUESTED)

    def reconciliation_status(self) -> str:
        return self.dashboard.summary().reconciliation_status

    def risk_status(self) -> dict[str, object]:
        summary = self.dashboard.summary()
        return {"kill_switch_active": summary.kill_switch_active, "risk_block_reasons": summary.risk_block_reasons, "go_live_allowed": False}

    def shadow_run_status(self) -> dict[str, object]:
        return asdict(self.shadow.status())

    def snapshot_status(self) -> dict[str, object]:
        if hasattr(self.audit_store, "latest_snapshot"):
            snapshot = self.audit_store.latest_snapshot()
            return {"available": snapshot is not None, "mode": snapshot.current_mode if snapshot else None, "go_live_allowed": False}
        return {"available": False, "go_live_allowed": False}

    def recovery_status(self) -> dict[str, object]:
        if self.recovery is None:
            return {"available": False, "go_live_allowed": False}
        return {**asdict(self.recovery.last_status), "go_live_allowed": False}

    def persistence_health(self) -> dict[str, object]:
        if hasattr(self.audit_store, "health"):
            return self.audit_store.health()
        return {"status": "memory", "go_live_allowed": False}

    def shadow_orchestrator_status(self) -> dict[str, object]:
        if self.orchestrator is None:
            return {"available": False, "go_live_allowed": False}
        return {"state": self.orchestrator.status.state.value, "reasons": self.orchestrator.status.reasons, "go_live_allowed": False}

    def daily_report_latest(self) -> dict[str, object]:
        events = self.audit_store.all_events()
        if not events:
            return {"available": False, "go_live_allowed": False}
        latest_day = max(event.timestamp.date() for event in events)
        return DailyShadowReportGenerator(self.audit_store).generate(latest_day).to_dict()

    def evidence_pack_metadata(self) -> dict[str, object]:
        pack = EvidencePackGenerator(self.audit_store, self.dashboard, self.shadow).generate(config_summary={"source": "api"})
        return pack.metadata

    def manual_review_checklist(self) -> dict[str, object]:
        result = ManualReviewGate().evaluate(self.shadow.status(), None, runbook_followed=False)
        return asdict(result)


    def strategies(self) -> tuple[object, ...]:
        registry = self.strategy_context.get("registry")
        if isinstance(registry, StrategyRegistry):
            return registry.all()
        return StrategyRegistry.with_defaults().all()

    def strategies_health(self) -> dict[str, object]:
        return dict(self.strategy_context.get("health_scores", {}))

    def strategies_allocations(self) -> object:
        return self.strategy_context.get("allocation_report", {"available": False, "go_live_allowed": False})

    def strategies_correlations(self) -> object:
        return self.strategy_context.get("correlation_report", {"available": False, "go_live_allowed": False})

    def strategies_unified_signal(self) -> object:
        return self.strategy_context.get("unified_signal", {"available": False, "go_live_allowed": False})

    def strategies_conflicts(self) -> object:
        signal = self.strategy_context.get("unified_signal")
        if signal is not None and hasattr(signal, "conflict_report"):
            return signal.conflict_report
        return {"available": False, "go_live_allowed": False}


    def execution_reports(self) -> object:
        return self.strategy_context.get("execution_reports", {"available": False, "go_live_allowed": False})

    def execution_latency(self) -> object:
        return self.strategy_context.get("execution_latency", {"available": False, "go_live_allowed": False})

    def execution_slippage(self) -> object:
        return self.strategy_context.get("execution_slippage", {"available": False, "go_live_allowed": False})

    def execution_impact(self) -> object:
        return self.strategy_context.get("execution_impact", {"available": False, "go_live_allowed": False})

    def execution_quality(self) -> object:
        return self.strategy_context.get("execution_quality", {"available": False, "go_live_allowed": False})

    def research_datasets(self) -> object:
        return self.strategy_context.get("research_datasets", {"available": False, "data_status": "DATA_UNAVAILABLE", "go_live_allowed": False})

    def research_features(self) -> object:
        return self.strategy_context.get("research_features", {"available": False, "data_status": "DATA_UNAVAILABLE", "go_live_allowed": False})

    def research_experiments(self) -> object:
        return self.strategy_context.get("research_experiments", {"available": False, "data_status": "DATA_UNAVAILABLE", "go_live_allowed": False})

    def research_reports(self) -> object:
        return self.strategy_context.get("research_reports", {"available": False, "data_status": "DATA_UNAVAILABLE", "go_live_allowed": False})

    def monitoring_metrics(self) -> object:
        return self.strategy_context.get("monitoring_metrics", {"available": False, "go_live_allowed": False})

    def monitoring_metrics_prometheus(self) -> object:
        return self.strategy_context.get("monitoring_metrics_prometheus", "")

    def monitoring_incidents(self) -> object:
        return self.strategy_context.get("monitoring_incidents", ())

    def monitoring_incidents_open(self) -> object:
        return self.strategy_context.get("monitoring_incidents_open", ())

    def monitoring_slo(self) -> object:
        return self.strategy_context.get("monitoring_slo", {"available": False, "go_live_allowed": False})

    def monitoring_alerts(self) -> object:
        return self.strategy_context.get("monitoring_alerts", ())

    def governance_events(self) -> object:
        return self.strategy_context.get("governance_events", ())

    def governance_policies(self) -> object:
        return self.strategy_context.get("governance_policies", {"available": False, "go_live_allowed": False})

    def governance_compliance(self) -> object:
        return self.strategy_context.get("governance_compliance", {"available": False, "go_live_allowed": False})

    def governance_audit_chain(self) -> object:
        return self.strategy_context.get("governance_audit_chain", {"available": False, "go_live_allowed": False})

    def governance_permissions(self) -> object:
        return self.strategy_context.get("governance_permissions", {"available": False, "go_live_allowed": False})

    def ha_status(self) -> object:
        return self.strategy_context.get("ha_status", {"available": False, "go_live_allowed": False})

    def ha_backups(self) -> object:
        return self.strategy_context.get("ha_backups", {"available": False, "go_live_allowed": False})

    def ha_restore(self) -> object:
        return self.strategy_context.get("ha_restore", {"available": False, "go_live_allowed": False})

    def ha_recovery(self) -> object:
        return self.strategy_context.get("ha_recovery", {"available": False, "go_live_allowed": False})

    def ha_business_continuity(self) -> object:
        return self.strategy_context.get("ha_business_continuity", {"available": False, "go_live_allowed": False})

    def certification_status(self) -> object:
        return self.strategy_context.get("certification_status", {"available": False, "go_live_allowed": False})

    def certification_scorecard(self) -> object:
        return self.strategy_context.get("certification_scorecard", {"available": False, "go_live_allowed": False})

    def certification_readiness(self) -> object:
        return self.strategy_context.get("certification_readiness", {"available": False, "go_live_allowed": False})

    def certification_evidence_quality(self) -> object:
        return self.strategy_context.get("certification_evidence_quality", {"available": False, "go_live_allowed": False})

    def certification_reviews(self) -> object:
        return self.strategy_context.get("certification_reviews", {"available": False, "go_live_allowed": False})

    def certification_package(self) -> object:
        return self.strategy_context.get("certification_package", {"available": False, "go_live_allowed": False})
