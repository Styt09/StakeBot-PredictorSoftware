from __future__ import annotations

import json
import importlib.util
from pathlib import Path

from institutional_trading_platform.broker import RealZerodhaProfileClient, ZerodhaAuthConfig, ZerodhaAuthService, ZerodhaConnectionStatus, ZerodhaProfileClientError
from institutional_trading_platform.runtime import RuntimeEventType, SQLiteAuditStore

_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "zerodha_profile_smoke_test.py"
_SPEC = importlib.util.spec_from_file_location("zerodha_profile_smoke_test", _SCRIPT_PATH)
assert _SPEC and _SPEC.loader
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
PROFILE_SMOKE_GO = _MODULE.PROFILE_SMOKE_GO
PROFILE_SMOKE_NO_GO = _MODULE.PROFILE_SMOKE_NO_GO
run_smoke = _MODULE.run_smoke

_AUDIT_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "zerodha_integration_audit.py"
_AUDIT_SPEC = importlib.util.spec_from_file_location("zerodha_integration_audit", _AUDIT_SCRIPT_PATH)
assert _AUDIT_SPEC and _AUDIT_SPEC.loader
_AUDIT_MODULE = importlib.util.module_from_spec(_AUDIT_SPEC)
_AUDIT_SPEC.loader.exec_module(_AUDIT_MODULE)
run_integration_audit = _AUDIT_MODULE.run_audit
load_env_with_dotenv = _MODULE.load_env_with_dotenv


class FakeHTTPResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_real_profile_client_success_response_passes() -> None:
    def opener(request, timeout):
        assert request.get_method() == "GET"
        assert request.full_url.endswith("/user/profile")
        assert "Authorization" in request.headers
        return FakeHTTPResponse({"status": "success", "data": {"user_id": "AB1234", "user_name": "Test"}})

    client = RealZerodhaProfileClient(opener=opener)
    state = ZerodhaAuthService(ZerodhaAuthConfig("key", "token", expected_user_id="AB1234"), profile_client=client).validate()
    assert state.status == ZerodhaConnectionStatus.CONNECTED
    assert state.profile_reachable is True
    assert state.user_id == "AB1234"
    assert state.go_live_allowed is False


def test_profile_client_network_error_fails_closed() -> None:
    def opener(request, timeout):
        raise OSError("network down access_token=secret")

    client = RealZerodhaProfileClient(opener=opener)
    state = ZerodhaAuthService(ZerodhaAuthConfig("key", "token"), profile_client=client).validate()
    assert state.status == ZerodhaConnectionStatus.ZERODHA_UNAVAILABLE
    assert state.profile_reachable is False
    assert "profile check failed" in state.reasons[0]
    assert "secret" not in state.reasons[0]


def test_missing_credentials_revoked_and_mismatched_user_fail() -> None:
    ok_client = RealZerodhaProfileClient(opener=lambda request, timeout: FakeHTTPResponse({"status": "success", "data": {"user_id": "ACTUAL"}}))
    revoked_client = RealZerodhaProfileClient(opener=lambda request, timeout: FakeHTTPResponse({"status": "success", "data": {"user_id": "ACTUAL", "revoked": True}}))

    missing_key = ZerodhaAuthService(ZerodhaAuthConfig("", "token"), profile_client=ok_client).validate()
    missing_token = ZerodhaAuthService(ZerodhaAuthConfig("key", ""), profile_client=ok_client).validate()
    revoked = ZerodhaAuthService(ZerodhaAuthConfig("key", "token"), profile_client=revoked_client).validate()
    mismatch = ZerodhaAuthService(ZerodhaAuthConfig("key", "token", expected_user_id="EXPECTED"), profile_client=ok_client).validate()

    assert missing_key.status == ZerodhaConnectionStatus.ZERODHA_UNAVAILABLE
    assert missing_token.status == ZerodhaConnectionStatus.ZERODHA_UNAVAILABLE
    assert revoked.status == ZerodhaConnectionStatus.ZERODHA_UNAVAILABLE
    assert mismatch.status == ZerodhaConnectionStatus.ZERODHA_UNAVAILABLE


def test_smoke_script_persists_redacted_pass_and_fail_events(tmp_path: Path) -> None:
    pass_client = RealZerodhaProfileClient(opener=lambda request, timeout: FakeHTTPResponse({"status": "success", "data": {"user_id": "AB1234"}}))
    pass_db = tmp_path / "pass.db"
    code, payload = run_smoke({"ZERODHA_API_KEY": "key", "ZERODHA_ACCESS_TOKEN": "token-secret", "ZERODHA_EXPECTED_USER_ID": "AB1234", "AUDIT_DB_PATH": str(pass_db)}, pass_client)
    assert code == 0
    assert payload["status"] == PROFILE_SMOKE_GO
    pass_events = SQLiteAuditStore(pass_db).all_events()
    assert pass_events[-1].event_type == RuntimeEventType.ZERODHA_READ_ONLY_PROFILE_SMOKE_PASSED
    assert pass_events[-1].payload["go_live_allowed"] is False
    assert "token-secret" not in json.dumps(pass_events[-1].payload)

    fail_db = tmp_path / "fail.db"
    code, payload = run_smoke({"ZERODHA_API_KEY": "key", "ZERODHA_ACCESS_TOKEN": "token", "ZERODHA_EXPECTED_USER_ID": "EXPECTED", "AUDIT_DB_PATH": str(fail_db)}, pass_client)
    assert code == 2
    assert payload["status"] == PROFILE_SMOKE_NO_GO
    fail_events = SQLiteAuditStore(fail_db).all_events()
    assert fail_events[-1].event_type == RuntimeEventType.ZERODHA_READ_ONLY_PROFILE_SMOKE_FAILED


def test_dotenv_visibility_uses_explicit_env_path(tmp_path: Path) -> None:
    env_file = tmp_path / "zerodha.env"
    env_file.write_text(
        "\n".join(
            (
                "ZERODHA_API_KEY=key-from-dotenv",
                "ZERODHA_API_SECRET=secret-from-dotenv",
                "ZERODHA_ACCESS_TOKEN=token-from-dotenv",
                "ZERODHA_EXPECTED_USER_ID=AB1234",
                f"AUDIT_DB_PATH={tmp_path / 'audit.db'}",
                "ZERODHA_INSTRUMENT_DUMP_PATH=/tmp/instruments.csv",
            )
        ),
        encoding="utf-8",
    )

    loaded = load_env_with_dotenv({"ZERODHA_ENV_PATH": str(env_file)})

    assert loaded["ZERODHA_API_KEY"] == "key-from-dotenv"
    assert loaded["ZERODHA_API_SECRET"] == "secret-from-dotenv"
    assert loaded["ZERODHA_ACCESS_TOKEN"] == "token-from-dotenv"
    assert loaded["ZERODHA_EXPECTED_USER_ID"] == "AB1234"
    assert loaded["ZERODHA_INSTRUMENT_DUMP_PATH"] == "/tmp/instruments.csv"


def test_profile_client_exposes_no_order_methods_and_static_scan_passes() -> None:
    client = RealZerodhaProfileClient(opener=lambda request, timeout: FakeHTTPResponse({"status": "success", "data": {"user_id": "AB1234"}}))
    assert not hasattr(client, "place_order")
    assert not hasattr(client, "submit_order")
    assert not hasattr(client, "order")


def test_profile_client_malformed_response_fails_closed() -> None:
    client = RealZerodhaProfileClient(opener=lambda request, timeout: FakeHTTPResponse({"status": "error", "message": "access_token=secret invalid"}))
    try:
        client.profile("key", "token")
    except ZerodhaProfileClientError as exc:
        assert "secret" not in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected fail-closed profile error")


def test_integration_audit_reports_missing_env_without_orders(tmp_path: Path) -> None:
    report = run_integration_audit({"AUDIT_DB_PATH": str(tmp_path / "audit.db")})
    assert report["status"] == "FAIL"
    assert report["checks"]["imports"]["status"] == "PASS"
    assert report["checks"]["market_data_mapping"]["status"] == "PASS"
    assert report["checks"]["profile_smoke"]["status"] == PROFILE_SMOKE_NO_GO
    assert report["go_live_allowed"] is False
    events = SQLiteAuditStore(tmp_path / "audit.db").all_events()
    assert events[-1].event_type == RuntimeEventType.ZERODHA_INTEGRATION_AUDIT_COMPLETED
    assert events[-1].payload["go_live_allowed"] is False
