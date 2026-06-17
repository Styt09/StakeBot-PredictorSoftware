from pathlib import Path
import re

from institutional_trading_platform.web_app import _live_order_submit

DOCS = [
    "FINAL_CTO_READINESS_REPORT.md",
    "PRODUCTION_RUNBOOK.md",
    "PAPER_TRADING_GUIDE.md",
    "SHADOW_TRADING_GUIDE.md",
    "BROKER_SAFETY_GUIDE.md",
    "KILL_SWITCH_RUNBOOK.md",
    "AUDIT_EVIDENCE_GUIDE.md",
    "GO_LIVE_NO_GO_CHECKLIST.md",
    "INCIDENT_RESPONSE_PLAN.md",
    "SYSTEM_STATUS_SUMMARY.md",
]

# Avoid false positives such as "risk-gate" while still detecting real secret-like values.
SECRET_PATTERNS = [
    re.compile(r"sk-(?:proj|live|test|svc|admin|org)[a-z0-9_-]{8,}", re.IGNORECASE),
    re.compile(r"api[_-]?secret\s*=\s*[^\s`'"]+", re.IGNORECASE),
    re.compile(r"access[_-]?token\s*=\s*[^\s`'"]+", re.IGNORECASE),
    re.compile(r"request[_-]?token\s*=\s*[^\s`'"]+", re.IGNORECASE),
    re.compile(r"password\s*=\s*[^\s`'"]+", re.IGNORECASE),
]


def test_phase12_docs_exist() -> None:
    for doc in DOCS:
        assert Path(doc).exists(), doc


def test_docs_include_live_no_go_and_go_live_false() -> None:
    for doc in DOCS:
        text = Path(doc).read_text().lower()
        assert "live: no-go" in text or "live remains no-go" in text or "live must remain no-go" in text, doc
        assert "go_live_allowed=false" in text, doc


def test_docs_do_not_expose_secret_like_values() -> None:
    combined = "\n".join(Path(doc).read_text() for doc in DOCS)
    for pattern in SECRET_PATTERNS:
        assert pattern.search(combined) is None, pattern.pattern


def test_docs_include_required_sections() -> None:
    final = Path("FINAL_CTO_READINESS_REPORT.md").read_text().lower()
    for phrase in ["paper trading status", "shadow trading status", "broker adapter safety status", "persistent kill switch status", "durable audit log status", "readiness gate status"]:
        assert phrase in final


def test_live_order_submit_remains_blocked() -> None:
    result = _live_order_submit({"preview_id": "missing", "typed_confirmation": "CONFIRM_LIVE_ORDER", "approval_mode": True})
    assert result["status"] == "BLOCKED"
    assert result["broker_order_id"] is None
    assert result["go_live_allowed"] is False
