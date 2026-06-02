"""Research operating system primitives.

This module provides deterministic registries and governance workflows for
research notebooks, experiments, backtests, approvals, audit trails, and
reproducibility manifests. It intentionally avoids notebook-server coupling so
it can run in CI, batch research jobs, and controlled production promotion
workflows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from typing import Mapping


class ApprovalStatus(StrEnum):
    """Lifecycle state for governed research artifacts."""

    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    RETIRED = "RETIRED"


@dataclass(frozen=True)
class ReproducibilityManifest:
    """Immutable inputs needed to reproduce a research or backtest run."""

    git_commit: str
    data_snapshot_id: str
    environment: Mapping[str, str]
    parameters: Mapping[str, str]
    random_seed: int

    def __post_init__(self) -> None:
        if not self.git_commit.strip() or not self.data_snapshot_id.strip():
            raise ValueError("git_commit and data_snapshot_id are required")
        if self.random_seed < 0:
            raise ValueError("random_seed cannot be negative")

    @property
    def manifest_hash(self) -> str:
        """Stable SHA-256 hash for reproducibility attestation."""

        payload = "|".join(
            [
                self.git_commit,
                self.data_snapshot_id,
                str(self.random_seed),
                *[f"env:{key}={self.environment[key]}" for key in sorted(self.environment)],
                *[f"param:{key}={self.parameters[key]}" for key in sorted(self.parameters)],
            ]
        )
        return sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ResearchNotebook:
    """Governed notebook metadata without storing notebook source inline."""

    notebook_id: str
    path: str
    owner: str
    strategy_family: str
    manifest: ReproducibilityManifest
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not all((self.notebook_id.strip(), self.path.strip(), self.owner.strip(), self.strategy_family.strip())):
            raise ValueError("notebook_id, path, owner, and strategy_family are required")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")


@dataclass(frozen=True)
class ExperimentRun:
    """Experiment tracking record for alpha, ML, AI, or risk research."""

    experiment_id: str
    name: str
    owner: str
    metrics: Mapping[str, float]
    artifacts: Mapping[str, str]
    manifest: ReproducibilityManifest
    status: ApprovalStatus = ApprovalStatus.DRAFT
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not all((self.experiment_id.strip(), self.name.strip(), self.owner.strip())):
            raise ValueError("experiment_id, name, and owner are required")
        for metric, value in self.metrics.items():
            if not metric.strip():
                raise ValueError("metric names cannot be blank")
            if not isinstance(value, int | float):
                raise ValueError("metric values must be numeric")


@dataclass(frozen=True)
class BacktestRecord:
    """Backtest registry record with governance-critical diagnostics."""

    backtest_id: str
    strategy_name: str
    owner: str
    start: datetime
    end: datetime
    metrics: Mapping[str, float]
    manifest: ReproducibilityManifest
    lookahead_bias_checked: bool
    survivorship_bias_checked: bool
    data_leakage_checked: bool
    status: ApprovalStatus = ApprovalStatus.DRAFT

    def __post_init__(self) -> None:
        if not all((self.backtest_id.strip(), self.strategy_name.strip(), self.owner.strip())):
            raise ValueError("backtest_id, strategy_name, and owner are required")
        if self.start >= self.end:
            raise ValueError("backtest start must be before end")
        if not all((self.lookahead_bias_checked, self.survivorship_bias_checked, self.data_leakage_checked)):
            raise ValueError("all backtest bias checks must pass before registration")


@dataclass(frozen=True)
class ResearchAuditEvent:
    """Append-only research audit trail event."""

    artifact_id: str
    actor: str
    action: str
    reason: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not all((self.artifact_id.strip(), self.actor.strip(), self.action.strip(), self.reason.strip())):
            raise ValueError("artifact_id, actor, action, and reason are required")


class ResearchRegistry:
    """In-memory research OS registry for deterministic services and tests."""

    def __init__(self) -> None:
        self._notebooks: dict[str, ResearchNotebook] = {}
        self._experiments: dict[str, ExperimentRun] = {}
        self._backtests: dict[str, BacktestRecord] = {}
        self._audit_events: list[ResearchAuditEvent] = []

    def register_notebook(self, notebook: ResearchNotebook) -> None:
        """Register a governed research notebook."""

        self._notebooks[notebook.notebook_id] = notebook
        self._audit_events.append(ResearchAuditEvent(notebook.notebook_id, notebook.owner, "REGISTER_NOTEBOOK", "Notebook registered"))

    def register_experiment(self, experiment: ExperimentRun) -> None:
        """Register an experiment run."""

        self._experiments[experiment.experiment_id] = experiment
        self._audit_events.append(ResearchAuditEvent(experiment.experiment_id, experiment.owner, "REGISTER_EXPERIMENT", "Experiment registered"))

    def register_backtest(self, backtest: BacktestRecord) -> None:
        """Register a bias-checked backtest."""

        self._backtests[backtest.backtest_id] = backtest
        self._audit_events.append(ResearchAuditEvent(backtest.backtest_id, backtest.owner, "REGISTER_BACKTEST", "Backtest registered"))

    def approve(self, artifact_id: str, approver: str, reason: str) -> None:
        """Record approval for any registered research artifact."""

        if artifact_id not in self.artifact_ids:
            raise ValueError(f"unknown artifact: {artifact_id}")
        self._audit_events.append(ResearchAuditEvent(artifact_id, approver, ApprovalStatus.APPROVED.value, reason))

    @property
    def artifact_ids(self) -> set[str]:
        """All registered research artifact identifiers."""

        return set(self._notebooks) | set(self._experiments) | set(self._backtests)

    def audit_trail(self, artifact_id: str | None = None) -> tuple[ResearchAuditEvent, ...]:
        """Return audit events, optionally filtered by artifact."""

        if artifact_id is None:
            return tuple(self._audit_events)
        return tuple(event for event in self._audit_events if event.artifact_id == artifact_id)
