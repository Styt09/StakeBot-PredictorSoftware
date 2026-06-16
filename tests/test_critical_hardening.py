from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pytest

from institutional_trading_platform.alpha_gate_x import (
    AlphaGateXSettings,
    AlphaSignal,
    OrderRouter,
    RealOrderPathForbidden,
    TradingMode,
    assert_real_order_path_forbidden,
)
from institutional_trading_platform.broker import ReadOnlyKiteTickerWrapper, ZerodhaAuthConfig, ZerodhaAuthService, ZerodhaConnectionStatus, ZerodhaShadowFeedRunner, ZerodhaWebSocketMarketDataAdapter
from institutional_trading_platform.runtime import DashboardSummaryService, EventBus, InMemoryAuditStore, RuntimeEvent, RuntimeEventType, ShadowRunValidator
from institutional_trading_platform.runtime.certification import CertificationStatus, FinalCertificationFramework
from institutional_trading_platform.runtime.evidence_pack import EvidencePackGenerator

UTC = timezone.utc


class LiveBrokerSpy:
    def __init__(self) -> None:
        self.called = False

    def place_order(self, request):  # pragma: no cover - must never execute
        self.called = True
        raise AssertionError("live broker place_order must never be called")


def test_live_broker_place_order_is_impossible() -> None:
    spy = LiveBrokerSpy()
    with pytest.raises(RealOrderPathForbidden):
        OrderRouter(AlphaGateXSettings(), live_broker=spy)
    assert spy.called is False
    assert assert_real_order_path_forbidden() is True
    assert AlphaGateXSettings(trading_mode=TradingMode.PAPER_TRADING).live_orders_enabled is False
    with pytest.raises(RealOrderPathForbidden, match="LIVE_AUTO"):
        AlphaGateXSettings(trading_mode=TradingMode.LIVE_AUTO, live_trading=True).validate_live_trading()


class ProfileOK:
    def profile(self, api_key: str, access_token: str) -> dict[str, object]:
        return {"user_id": "AB1234", "revoked": False}


class ProfileFailure:
    def profile(self, api_key: str, access_token: str) -> dict[str, object]:
        raise RuntimeError("auth failed")


def test_zerodha_profile_success_and_fail_closed() -> None:
    ok = ZerodhaAuthService(ZerodhaAuthConfig("key", "token", expected_user_id="AB1234"), profile_client=ProfileOK()).validate()
    assert ok.status == ZerodhaConnectionStatus.CONNECTED
    assert ok.profile_reachable is True
    assert ok.user_id == "AB1234"
    assert ok.go_live_allowed is False

    failed = ZerodhaAuthService(ZerodhaAuthConfig("key", "token"), profile_client=ProfileFailure()).validate()
    assert failed.status == ZerodhaConnectionStatus.ZERODHA_UNAVAILABLE
    assert "profile check failed" in failed.reasons[0]

    revoked = ZerodhaAuthService(ZerodhaAuthConfig("key", "token"), profile_client=type("Revoked", (), {"profile": lambda self, api_key, access_token: {"user_id": "AB1234", "revoked": True}})()).validate()
    assert revoked.status == ZerodhaConnectionStatus.ZERODHA_UNAVAILABLE

    mismatch = ZerodhaAuthService(ZerodhaAuthConfig("key", "token", expected_user_id="EXPECTED"), profile_client=ProfileOK()).validate()
    assert mismatch.status == ZerodhaConnectionStatus.ZERODHA_UNAVAILABLE


def test_shadow_feed_runner_rejects_malformed_duplicates_and_detects_stale() -> None:
    bus = EventBus()
    adapter = ZerodhaWebSocketMarketDataAdapter({101: ("RELIANCE", "NSE")}, event_bus=bus)
    runner = ZerodhaShadowFeedRunner(adapter, stale_after=timedelta(seconds=5), event_bus=bus)
    runner.resolve_and_subscribe((101,))
    runner.start()

    malformed = runner.on_payload({"instrument_token": 999, "last_price": 0})
    assert not malformed.ok
    assert runner.status().malformed_ticks == 1

    ts = datetime(2026, 1, 1, 9, 15, tzinfo=UTC)
    first = runner.on_payload({"instrument_token": 101, "last_price": 100.0, "exchange_timestamp": ts, "last_trade_id": "dup"}, received_at=ts)
    duplicate = runner.on_payload({"instrument_token": 101, "last_price": 100.0, "exchange_timestamp": ts, "last_trade_id": "dup"}, received_at=ts)
    assert first.ok
    assert not duplicate.ok
    assert "duplicate tick" in duplicate.reasons
    stale = runner.heartbeat(ts + timedelta(seconds=10))
    assert stale.stale_symbols == ("RELIANCE",)
    assert any(event.event_type == RuntimeEventType.ALERT_EMITTED for event in bus.events)


class FakeTicker:
    def __init__(self, api_key: str, access_token: str) -> None:
        self.api_key = api_key
        self.access_token = access_token
        self.on_ticks = None
        self.on_connect = None
        self.on_close = None
        self.on_error = None
        self.subscribed = ()
        self.closed = False

    def connect(self, threaded: bool = True) -> None:
        if self.on_connect is not None:
            self.on_connect(self, {"threaded": threaded})

    def subscribe(self, tokens) -> None:
        self.subscribed = tuple(tokens)

    def close(self) -> None:
        self.closed = True
        if self.on_close is not None:
            self.on_close(self, 1000, "closed")


def test_read_only_ticker_wrapper_subscribes_and_validates_ticks_only() -> None:
    bus = EventBus()
    wrapper = ReadOnlyKiteTickerWrapper(
        api_key="key",
        access_token="token",
        token_to_symbol={101: ("RELIANCE", "NSE")},
        ticker_factory=FakeTicker,
        stale_after=timedelta(seconds=5),
        event_bus=bus,
    )

    connected = wrapper.connect()
    subscribed = wrapper.subscribe((101, 999))
    ts = datetime(2026, 1, 1, 9, 15, tzinfo=UTC)
    assert wrapper.ticker.on_ticks is not None
    wrapper.ticker.on_ticks(wrapper.ticker, ({"instrument_token": 101, "last_price": 100.0, "exchange_timestamp": ts, "last_trade_id": "t1"},))
    wrapper.ticker.on_ticks(wrapper.ticker, ({"instrument_token": 101, "last_price": 100.0, "exchange_timestamp": ts, "last_trade_id": "t1"}, {"instrument_token": 999, "last_price": 0}))
    status = wrapper.heartbeat(ts + timedelta(seconds=1))
    closed = wrapper.shutdown()

    assert connected.connected is True
    assert subscribed.subscribed_tokens == (101,)
    assert status.ticks_seen == 1
    assert status.duplicate_ticks == 1
    assert status.malformed_ticks == 1
    assert status.go_live_allowed is False
    assert closed.connected is False
    assert any(event.event_type == RuntimeEventType.ZERODHA_CONNECTED for event in bus.events)


def test_run_shadow_day_exits_no_go_when_prerequisites_missing() -> None:
    completed = subprocess.run([sys.executable, "scripts/run_shadow_day.py"], text=True, capture_output=True, check=False)
    assert completed.returncode == 2
    assert "NO_GO_SHADOW_READINESS" in completed.stdout


def test_evidence_provenance_included_and_missing_blocks_certification() -> None:
    store = InMemoryAuditStore()
    store.append(RuntimeEvent(RuntimeEventType.RUNTIME_HEARTBEAT, payload={"ok": True}))
    pack = EvidencePackGenerator(store, DashboardSummaryService(store), ShadowRunValidator(store)).generate(config_summary={"profile": "LOCAL"})
    audit_section = pack.sections["audit_events_json"]
    assert audit_section["provenance"]["source_store"].endswith("InMemoryAuditStore")
    assert audit_section["provenance"]["event_id_range"]
    assert audit_section["go_live_allowed"] is False

    framework = FinalCertificationFramework()
    report = framework.certify_area(next(area for area in framework.AREA_EVIDENCE if area.value == "Market Data"), {"audit_events_json": {"data": []}})
    assert report.status == CertificationStatus.FAIL
    assert any("missing provenance" in failure for failure in report.failures)


def test_no_order_placement_endpoint_and_static_scan_passes() -> None:
    assert subprocess.run([sys.executable, "scripts/no_live_order_static_scan.py"], capture_output=True, text=True, check=False).returncode == 0
