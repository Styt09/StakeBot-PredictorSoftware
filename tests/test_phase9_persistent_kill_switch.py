from pathlib import Path

from institutional_trading_platform.persistent_kill_switch import (
    PersistentKillSwitch,
    RESET_CONFIRMATION,
    UNREADABLE_REASON,
)
from institutional_trading_platform.risk_engine import RiskEngine, RiskInput
from institutional_trading_platform.web_app import _live_order_submit
from institutional_trading_platform.broker_adapter import BlockedBrokerMutationAdapter


GOOD_HEALTH = {"state": "CONNECTED", "missingData": False, "marketOpen": True, "blockedReasons": ()}
GOOD_SIGNAL = {
    "symbol": "RELIANCE",
    "action": "BUY",
    "entry": 100.0,
    "stop_loss": 98.0,
    "targets": (104.0,),
    "confidence": 80.0,
    "risk_reward": 2.0,
    "go_live_allowed": False,
}


def _risk_input(kill_switch_active: bool = False) -> RiskInput:
    return RiskInput(
        symbol="RELIANCE",
        side="BUY",
        quantity=1,
        signal=GOOD_SIGNAL,
        market_health=GOOD_HEALTH,
        account_state={"realized_pnl": 0},
        open_positions=(),
        order_path="PAPER",
        kill_switch_active=kill_switch_active,
    )


def test_default_kill_switch_status_is_inactive(tmp_path: Path) -> None:
    switch = PersistentKillSwitch(tmp_path / "kill_switch.json")
    status = switch.status()
    assert status["active"] is False
    assert status["go_live_allowed"] is False


def test_activate_persists_state_to_json(tmp_path: Path) -> None:
    path = tmp_path / "kill_switch.json"
    switch = PersistentKillSwitch(path)
    result = switch.activate({"reason": "manual safety stop", "activated_by": "operator"})
    assert result["status"] == "ACTIVE"
    assert path.exists()
    status = PersistentKillSwitch(path).status()
    assert status["active"] is True
    assert status["reason"] == "manual safety stop"
    assert status["go_live_allowed"] is False


def test_reset_without_confirmation_is_blocked(tmp_path: Path) -> None:
    switch = PersistentKillSwitch(tmp_path / "kill_switch.json")
    switch.activate({"reason": "test"})
    result = switch.reset({"typed_confirmation": "WRONG"})
    assert result["status"] == "BLOCKED"
    assert result["reason"] == "RESET_CONFIRMATION_REQUIRED"
    assert switch.status()["active"] is True


def test_reset_with_confirmation_clears_active_state(tmp_path: Path) -> None:
    switch = PersistentKillSwitch(tmp_path / "kill_switch.json")
    switch.activate({"reason": "test"})
    result = switch.reset({"typed_confirmation": RESET_CONFIRMATION, "reset_by": "operator"})
    assert result["status"] == "RESET"
    status = switch.status()
    assert status["active"] is False
    assert status["reset_by"] == "operator"
    assert status["go_live_allowed"] is False


def test_corrupt_json_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "kill_switch.json"
    path.write_text("not-json")
    status = PersistentKillSwitch(path).status()
    assert status["active"] is True
    assert status["reason"] == UNREADABLE_REASON
    assert status["go_live_allowed"] is False


def test_active_kill_switch_blocks_risk_engine() -> None:
    result = RiskEngine().evaluate(_risk_input(kill_switch_active=True))
    assert result["allowed"] is False
    assert "KILL_SWITCH_ACTIVE" in result["blocked_reasons"]
    assert result["go_live_allowed"] is False


def test_broker_mutation_remains_blocked() -> None:
    result = BlockedBrokerMutationAdapter().place_order({"symbol": "RELIANCE"})
    assert result["status"] == "BLOCKED"
    assert result["broker_order_id"] is None
    assert result["go_live_allowed"] is False


def test_live_order_submit_remains_blocked() -> None:
    result = _live_order_submit({"preview_id": "missing", "typed_confirmation": "CONFIRM_LIVE_ORDER", "approval_mode": True})
    assert result["status"] == "BLOCKED"
    assert result["broker_order_id"] is None
    assert result["go_live_allowed"] is False
