from institutional_trading_platform.readiness_gates import ReadinessGateEvaluator, ReadinessInputs
from institutional_trading_platform.web_app import _live_order_submit
from institutional_trading_platform.broker_adapter import BlockedBrokerMutationAdapter


def _inputs(**overrides):
    payload = {
        "broker_health": {"broker": "ZERODHA", "connected": True, "read_only": True, "mutation_enabled": False, "status": "CONNECTED", "go_live_allowed": False},
        "market_data_health": {"state": "CONNECTED", "marketOpen": True, "missingData": False, "go_live_allowed": False},
        "kill_switch_status": {"active": False, "reason": "", "go_live_allowed": False},
        "audit_report": {"total_events": 3, "go_live_allowed": False},
        "live_order_status": {"status": "BLOCKED", "broker_order_id": None, "go_live_allowed": False},
        "broker_mutation_status": {"status": "BLOCKED", "broker_order_id": None, "go_live_allowed": False},
        "paper_status": {"validation_status": "VALIDATED", "go_live_allowed": False},
        "shadow_status": {"enabled": True, "go_live_allowed": False},
        "public_config": {"trading_mode": "PAPER", "live_trading_enabled": False, "go_live_allowed": False},
    }
    payload.update(overrides)
    return ReadinessInputs(**payload)


def test_readiness_output_has_required_fields() -> None:
    result = ReadinessGateEvaluator().evaluate(_inputs())
    for key in ["paper_ready", "shadow_ready", "live_ready", "live_verdict", "blocked_reasons", "warnings", "evidence", "timestamp", "go_live_allowed"]:
        assert key in result
    assert result["go_live_allowed"] is False


def test_paper_and_shadow_can_be_ready_when_components_exist() -> None:
    result = ReadinessGateEvaluator().evaluate(_inputs())
    assert result["paper_ready"] is True
    assert result["shadow_ready"] is True
    assert result["live_ready"] is False
    assert result["live_verdict"] == "NO_GO"


def test_kill_switch_active_blocks_readiness() -> None:
    result = ReadinessGateEvaluator().evaluate(_inputs(kill_switch_status={"active": True, "reason": "stop", "go_live_allowed": False}))
    assert result["paper_ready"] is False
    assert result["shadow_ready"] is False
    assert "KILL_SWITCH_ACTIVE" in result["blocked_reasons"]


def test_missing_audit_log_blocks_readiness() -> None:
    result = ReadinessGateEvaluator().evaluate(_inputs(audit_report={"total_events": 0, "go_live_allowed": False}))
    assert result["paper_ready"] is False
    assert "AUDIT_EVIDENCE_MISSING" in result["blocked_reasons"]


def test_broker_mutation_disabled_is_required() -> None:
    result = ReadinessGateEvaluator().evaluate(_inputs(broker_health={"mutation_enabled": True, "read_only": False, "go_live_allowed": False}))
    assert "BROKER_MUTATION_NOT_DISABLED" in result["blocked_reasons"]


def test_reports_do_not_expose_secrets() -> None:
    result = ReadinessGateEvaluator().evaluate(_inputs(public_config={"trading_mode": "PAPER", "live_trading_enabled": False, "api_secret": "hidden", "access_token": "hidden", "go_live_allowed": False}))
    text = str(result)
    assert "api_secret" not in text.lower()
    assert "access_token" not in text.lower()
    assert result["go_live_allowed"] is False


def test_checklist_reports_live_not_implemented() -> None:
    evaluator = ReadinessGateEvaluator()
    gates = evaluator.evaluate(_inputs())
    checklist = evaluator.checklist(gates)
    assert checklist["live_verdict"] == "NO_GO"
    assert any(item["name"] == "live_ready" and item["status"] == "NOT_IMPLEMENTED" for item in checklist["items"])
    assert checklist["go_live_allowed"] is False


def test_live_order_submit_remains_blocked() -> None:
    result = _live_order_submit({"preview_id": "missing", "typed_confirmation": "CONFIRM_LIVE_ORDER", "approval_mode": True})
    assert result["status"] == "BLOCKED"
    assert result["broker_order_id"] is None
    assert result["go_live_allowed"] is False


def test_broker_order_place_remains_blocked() -> None:
    result = BlockedBrokerMutationAdapter().place_order({"symbol": "RELIANCE"})
    assert result["status"] == "BLOCKED"
    assert result["broker_order_id"] is None
    assert result["go_live_allowed"] is False
