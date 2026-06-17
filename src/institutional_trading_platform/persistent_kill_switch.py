"""Persistent kill switch for ALPHA-GATE X.

Phase 9 adds a durable safety stop that survives app restarts. It is fail-closed:
if the state file is corrupt or unreadable, the switch is treated as active.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4
import json

DEFAULT_STATE_PATH = Path(".alpha_gate_state") / "kill_switch.json"
RESET_CONFIRMATION = "RESET_KILL_SWITCH"
UNREADABLE_REASON = "KILL_SWITCH_STATE_UNREADABLE"


@dataclass(frozen=True)
class KillSwitchState:
    active: bool = False
    reason: str = ""
    activated_at: str | None = None
    activated_by: str | None = None
    reset_at: str | None = None
    reset_by: str | None = None
    event_id: str | None = None
    go_live_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "active": bool(self.active),
            "reason": self.reason,
            "activated_at": self.activated_at,
            "activated_by": self.activated_by,
            "reset_at": self.reset_at,
            "reset_by": self.reset_by,
            "event_id": self.event_id,
            "go_live_allowed": False,
        }


class PersistentKillSwitch:
    def __init__(self, path: str | Path = DEFAULT_STATE_PATH) -> None:
        self.path = Path(path)

    def status(self) -> dict[str, Any]:
        return self._read_state().to_dict()

    def is_active(self) -> bool:
        return bool(self._read_state().active)

    def activate(self, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        payload = dict(payload or {})
        now = _now()
        state = KillSwitchState(
            active=True,
            reason=str(payload.get("reason") or "manual safety stop"),
            activated_at=now,
            activated_by=str(payload.get("activated_by") or "operator"),
            reset_at=None,
            reset_by=None,
            event_id=f"kill-{uuid4()}",
            go_live_allowed=False,
        )
        self._write_state(state)
        return {"status": "ACTIVE", "kill_switch": state.to_dict(), "go_live_allowed": False}

    def reset(self, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        payload = dict(payload or {})
        if str(payload.get("typed_confirmation") or "") != RESET_CONFIRMATION:
            return {
                "status": "BLOCKED",
                "reason": "RESET_CONFIRMATION_REQUIRED",
                "required_confirmation": RESET_CONFIRMATION,
                "kill_switch": self.status(),
                "go_live_allowed": False,
            }
        current = self._read_state()
        state = KillSwitchState(
            active=False,
            reason="reset",
            activated_at=current.activated_at,
            activated_by=current.activated_by,
            reset_at=_now(),
            reset_by=str(payload.get("reset_by") or "operator"),
            event_id=f"kill-reset-{uuid4()}",
            go_live_allowed=False,
        )
        self._write_state(state)
        return {"status": "RESET", "kill_switch": state.to_dict(), "go_live_allowed": False}

    def _read_state(self) -> KillSwitchState:
        if not self.path.exists():
            return KillSwitchState(active=False, event_id="kill-default-inactive", go_live_allowed=False)
        try:
            raw = json.loads(self.path.read_text())
            if not isinstance(raw, dict):
                raise ValueError("kill switch state must be object")
            return KillSwitchState(
                active=bool(raw.get("active", False)),
                reason=str(raw.get("reason") or ""),
                activated_at=_optional_str(raw.get("activated_at")),
                activated_by=_optional_str(raw.get("activated_by")),
                reset_at=_optional_str(raw.get("reset_at")),
                reset_by=_optional_str(raw.get("reset_by")),
                event_id=_optional_str(raw.get("event_id")),
                go_live_allowed=False,
            )
        except Exception:
            return KillSwitchState(
                active=True,
                reason=UNREADABLE_REASON,
                activated_at=_now(),
                activated_by="system",
                reset_at=None,
                reset_by=None,
                event_id=f"kill-unreadable-{uuid4()}",
                go_live_allowed=False,
            )

    def _write_state(self, state: KillSwitchState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(state.to_dict(), indent=2, sort_keys=True) + "\n")


def block_payload(reason: str = "KILL_SWITCH_ACTIVE") -> dict[str, Any]:
    return {
        "status": "BLOCKED",
        "reason": reason,
        "blocked_reasons": (reason,),
        "go_live_allowed": False,
    }


def _optional_str(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _now() -> str:
    return datetime.now(UTC).isoformat()
