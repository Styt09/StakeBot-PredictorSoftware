from __future__ import annotations

from pathlib import Path

from institutional_trading_platform.ai_error_doctor import accuracy_gate_rules, diagnose_local_error, latest_error_report
from institutional_trading_platform.openai_auditor import (
    OpenAIReadOnlyAuditor,
    audit_signal_with_openai,
    deterministic_signal_audit,
    get_openai_auditor_config,
    mask_openai_key,
)
from institutional_trading_platform.web_app import _live_order_submit


GOOD_QUOTE = {
    "symbol": "RELIANCE",
    "ltp": 1332.7,
    "validation_status": "VALIDATED",
    "connection_status": "ZERODHA_READ_ONLY_CONNECTED",
    "go_live_allowed": False,
}
GOOD_HISTORY = {
    "symbol": "RELIANCE",
    "validation_status": "VALIDATED",
    "candles": [{"open": 1, "high": 2, "low": 1, "close": 2, "volume": 1000} for _ in range(25)],
    "go_live_allowed": False,
}
GOOD_SIGNAL = {
    "symbol": "RELIANCE",
    "decision": "BUY",
    "entry": 1332.7,
    "stop_loss": 1320.0,
    "target_1": 1360.0,
    "risk_reward": 2.0,
    "confidence_score": 82,
    "validation_status": "VALIDATED",
    "go_live_allowed": False,
}


def test_openai_key_missing_returns_unavailable(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = audit_signal_with_openai(symbol="RELIANCE", signal=GOOD_SIGNAL, market_quote=GOOD_QUOTE, market_history=GOOD_HISTORY)
    assert result["status"] in {"OPENAI_UNAVAILABLE", "PASS"}
    assert result["can_place_real_order"] is False
    assert result["go_live_allowed"] is False


def test_api_key_masking_never_exposes_full_key():
    key = "sk-proj_abcdefghijklmnopqrstuvwxyz1234567890"
    masked = mask_openai_key(key)
    assert key not in masked
    assert "len=" in masked


def test_ai_health_safe_flags(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj_testvalue")
    auditor = OpenAIReadOnlyAuditor(get_openai_auditor_config())
    health = auditor.health()
    assert health["go_live_allowed"] is False
    assert health["can_place_orders"] is False
    assert health["can_modify_files"] is False
    assert health["autofix_enabled"] is False


def test_local_audit_blocks_data_unavailable_quote():
    result = deterministic_signal_audit(signal=GOOD_SIGNAL, market_quote={"validation_status": "DATA_UNAVAILABLE"}, market_history=GOOD_HISTORY)
    assert result["final_action"] == "DATA_UNAVAILABLE"
    assert "VALIDATED_QUOTE_REQUIRED" in result["blocked_reasons"]
    assert result["go_live_allowed"] is False


def test_local_audit_blocks_missing_candles():
    result = deterministic_signal_audit(signal=GOOD_SIGNAL, market_quote=GOOD_QUOTE, market_history={"validation_status": "DATA_UNAVAILABLE"})
    assert result["final_action"] == "DATA_UNAVAILABLE"
    assert "VALIDATED_CANDLES_REQUIRED" in result["blocked_reasons"]


def test_local_audit_blocks_insufficient_candles():
    history = {**GOOD_HISTORY, "candles": GOOD_HISTORY["candles"][:5]}
    result = deterministic_signal_audit(signal=GOOD_SIGNAL, market_quote=GOOD_QUOTE, market_history=history)
    assert result["final_action"] == "NO_TRADE"
    assert "MINIMUM_21_CANDLES_REQUIRED" in result["blocked_reasons"]


def test_local_audit_blocks_low_confidence():
    signal = {**GOOD_SIGNAL, "confidence_score": 30}
    result = deterministic_signal_audit(signal=signal, market_quote=GOOD_QUOTE, market_history=GOOD_HISTORY)
    assert result["final_action"] == "NO_TRADE"
    assert any(reason.startswith("CONFIDENCE_BELOW") for reason in result["blocked_reasons"])


def test_local_audit_blocks_missing_stop_loss():
    signal = dict(GOOD_SIGNAL)
    signal.pop("stop_loss")
    result = deterministic_signal_audit(signal=signal, market_quote=GOOD_QUOTE, market_history=GOOD_HISTORY)
    assert result["final_action"] == "NO_TRADE"
    assert "STOP_LOSS_REQUIRED" in result["blocked_reasons"]


def test_local_audit_blocks_missing_target():
    signal = dict(GOOD_SIGNAL)
    signal.pop("target_1")
    result = deterministic_signal_audit(signal=signal, market_quote=GOOD_QUOTE, market_history=GOOD_HISTORY)
    assert result["final_action"] == "NO_TRADE"
    assert "TARGET_REQUIRED" in result["blocked_reasons"]


def test_local_audit_blocks_low_risk_reward():
    signal = {**GOOD_SIGNAL, "risk_reward": 0.5}
    result = deterministic_signal_audit(signal=signal, market_quote=GOOD_QUOTE, market_history=GOOD_HISTORY)
    assert result["final_action"] == "NO_TRADE"
    assert any(reason.startswith("RISK_REWARD_BELOW") for reason in result["blocked_reasons"])


def test_local_audit_never_upgrades_no_trade_to_buy():
    signal = {**GOOD_SIGNAL, "decision": "NO_TRADE"}
    result = deterministic_signal_audit(signal=signal, market_quote=GOOD_QUOTE, market_history=GOOD_HISTORY)
    assert result["original_action"] == "NO_TRADE"
    assert result["final_action"] != "BUY"


def test_local_audit_never_upgrades_data_unavailable_to_buy():
    signal = {**GOOD_SIGNAL, "decision": "DATA_UNAVAILABLE"}
    result = deterministic_signal_audit(signal=signal, market_quote=GOOD_QUOTE, market_history=GOOD_HISTORY)
    assert result["original_action"] == "DATA_UNAVAILABLE"
    assert result["final_action"] != "BUY"


def test_error_doctor_handles_missing_log_safely(tmp_path, monkeypatch):
    monkeypatch.setenv("ZERODHA_ACCESS_TOKEN", "token")
    instrument = tmp_path / "instruments.csv"
    instrument.write_text("exchange,tradingsymbol,instrument_token\nNSE,RELIANCE,1\n")
    monkeypatch.setenv("ZERODHA_INSTRUMENT_DUMP_PATH", str(instrument))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj_test")
    result = diagnose_local_error(log_path=tmp_path / "missing.log")
    assert result["status"] == "NO_LOG_AVAILABLE"
    assert result["go_live_allowed"] is False


def test_error_doctor_detects_instrument_csv_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("ZERODHA_ACCESS_TOKEN", "token")
    monkeypatch.setenv("ZERODHA_INSTRUMENT_DUMP_PATH", str(tmp_path / "missing.csv"))
    result = diagnose_local_error(log_path=tmp_path / "missing.log")
    assert result["category"] == "DATA"
    assert "instrument CSV" in result["root_cause"]
    assert result["go_live_allowed"] is False


def test_error_doctor_detects_token_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("ZERODHA_ACCESS_TOKEN", raising=False)
    result = diagnose_local_error(log_path=tmp_path / "missing.log")
    assert result["category"] == "BROKER"
    assert "access token" in result["root_cause"].lower()
    assert result["can_place_real_order"] is False


def test_accuracy_gates_safe_json():
    gates = accuracy_gate_rules()
    assert gates["go_live_allowed"] is False
    assert "validated quote required" in gates["rules"]
    assert gates["can_place_real_order"] is False


def test_latest_error_report_safe(monkeypatch, tmp_path):
    monkeypatch.delenv("ZERODHA_ACCESS_TOKEN", raising=False)
    report = latest_error_report()
    assert report["go_live_allowed"] is False
    assert report["can_place_real_order"] is False


def test_real_live_order_submit_remains_blocked():
    result = _live_order_submit({"typed_confirmation": "CONFIRM_LIVE_ORDER", "approval_mode": True})
    assert result["status"] == "BLOCKED"
    assert result["broker_order_id"] is None
    assert result["go_live_allowed"] is False


def test_phase10_patch_script_contains_endpoints():
    text = Path("scripts/patch_phase10_openai_auditor.py").read_text()
    for endpoint in ["/api/ai/health", "/api/ai/diagnose", "/api/ai/error-report", "/api/ai/accuracy-gates", "/api/ai/audit-signal"]:
        assert endpoint in text
