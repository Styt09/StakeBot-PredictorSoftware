from pathlib import Path

from institutional_trading_platform.durable_audit_log import AuditEvent, DurableAuditLog, AuditWriteError
from institutional_trading_platform.web_app import _live_order_submit

SECRET_TEXT = "secret-token-123"


def test_audit_logger_writes_jsonl_event(tmp_path: Path) -> None:
    log = DurableAuditLog(tmp_path / "audit.jsonl")
    event = log.write_event(AuditEvent(event_type="SYSTEM_START", source="TEST", status="PASS"))
    assert event["event_type"] == "SYSTEM_START"
    assert (tmp_path / "audit.jsonl").exists()
    assert event["go_live_allowed"] is False


def test_audit_logger_reads_recent_events(tmp_path: Path) -> None:
    log = DurableAuditLog(tmp_path / "audit.jsonl")
    for idx in range(3):
        log.write_event({"event_type": "RISK_CHECK_EVALUATED", "source": "TEST", "status": "PASS", "symbol": f"SYM{idx}"})
    recent = log.recent(limit=2)
    assert recent["total_events"] == 3
    assert len(recent["events"]) == 2
    assert recent["go_live_allowed"] is False


def test_audit_logger_sanitizes_secrets(tmp_path: Path) -> None:
    log = DurableAuditLog(tmp_path / "audit.jsonl")
    event = log.write_event({
        "event_type": "BROKER_HEALTH_CHECKED",
        "source": "BROKER",
        "status": "CONNECTED",
        "metadata": {"access_token": SECRET_TEXT, "api_secret": SECRET_TEXT, "nested": {"request_token": SECRET_TEXT}},
    })
    text = str(event) + (tmp_path / "audit.jsonl").read_text()
    assert SECRET_TEXT not in text
    assert "***MASKED***" in text


def test_audit_logger_handles_corrupt_lines_safely(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    path.write_text('{"event_type":"SYSTEM_START","source":"TEST","status":"PASS"}\nnot-json\n')
    events = DurableAuditLog(path).export_events()["events"]
    assert events[0]["event_type"] == "SYSTEM_START"
    assert events[1]["event_type"] == "AUDIT_LINE_UNREADABLE"
    assert events[1]["go_live_allowed"] is False


def test_audit_report_summarizes_counts(tmp_path: Path) -> None:
    log = DurableAuditLog(tmp_path / "audit.jsonl")
    log.write_event({"event_type": "RISK_CHECK_EVALUATED", "source": "RISK", "status": "BLOCKED", "symbol": "RELIANCE", "blocked_reasons": ("MARKET_CLOSED",)})
    log.write_event({"event_type": "RISK_CHECK_EVALUATED", "source": "RISK", "status": "PASS", "symbol": "TCS"})
    report = log.report()
    assert report["counts_by_event_type"]["RISK_CHECK_EVALUATED"] == 2
    assert report["counts_by_status"]["BLOCKED"] == 1
    assert report["counts_by_symbol"]["RELIANCE"] == 1
    assert report["counts_by_blocked_reason"]["MARKET_CLOSED"] == 1
    assert report["go_live_allowed"] is False


def test_audit_export_returns_safe_events(tmp_path: Path) -> None:
    log = DurableAuditLog(tmp_path / "audit.jsonl")
    log.write_event({"event_type": "BROKER_MUTATION_BLOCKED", "source": "BROKER", "status": "BLOCKED", "broker_order_id": "should-not-store"})
    exported = log.export_events()
    assert exported["events"][0]["broker_order_id"] is None
    assert exported["go_live_allowed"] is False


def test_live_order_submit_remains_blocked() -> None:
    result = _live_order_submit({"preview_id": "missing", "typed_confirmation": "CONFIRM_LIVE_ORDER", "approval_mode": True})
    assert result["status"] == "BLOCKED"
    assert result["broker_order_id"] is None
    assert result["go_live_allowed"] is False
