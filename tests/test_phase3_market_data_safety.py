from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from institutional_trading_platform.market_data_safety import (
    ExistingDataProvider,
    MarketDataHealthService,
    is_market_open,
    stale_data_block_payload,
)
from institutional_trading_platform.web_app import _live_order_submit, _market_history, _market_quote


class FakeProvider:
    def __init__(self, quote_payload):
        self.quote_payload = quote_payload

    def quote(self, symbol: str):
        return dict(self.quote_payload, symbol=symbol)

    def history(self, symbol: str, interval: str = "5minute"):
        return {"symbol": symbol, "interval": interval, "candles": (), "validation_status": "DATA_UNAVAILABLE", "go_live_allowed": False}


def test_missing_data_returns_data_unavailable_health() -> None:
    provider = FakeProvider({"ltp": "DATA_UNAVAILABLE", "last_update": "DATA_UNAVAILABLE", "validation_status": "DATA_UNAVAILABLE", "data_source": "DATA_UNAVAILABLE"})
    payload = MarketDataHealthService(provider).health("RELIANCE", now=datetime(2026, 1, 5, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata")))
    assert payload["state"] == "DATA_UNAVAILABLE"
    assert payload["missingData"] is True
    assert payload["go_live_allowed"] is False


def test_stale_data_returns_stale() -> None:
    now = datetime(2026, 1, 5, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    provider = FakeProvider({"ltp": 100.0, "last_update": (now - timedelta(seconds=20)).isoformat(), "validation_status": "VALIDATED", "data_source": "TEST_QUOTE"})
    payload = MarketDataHealthService(provider, stale_after_seconds=10, reconnecting_after_seconds=30).health("RELIANCE", now=now)
    assert payload["state"] == "STALE"
    assert "MARKET_DATA_STALE" in payload["blockedReasons"]


def test_fresh_quote_returns_connected() -> None:
    now = datetime(2026, 1, 5, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    provider = FakeProvider({"ltp": 100.0, "last_update": now.isoformat(), "validation_status": "VALIDATED", "data_source": "TEST_QUOTE"})
    payload = MarketDataHealthService(provider).health("RELIANCE", now=now)
    assert payload["state"] == "CONNECTED"
    assert payload["missingData"] is False


def test_market_closed_state_is_represented() -> None:
    sunday = datetime(2026, 1, 4, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    assert is_market_open(sunday) is False
    provider = FakeProvider({"ltp": 100.0, "last_update": sunday.isoformat(), "validation_status": "VALIDATED", "data_source": "TEST_QUOTE"})
    payload = MarketDataHealthService(provider).health("RELIANCE", now=sunday)
    assert payload["marketOpen"] is False
    assert payload["marketStatus"] == "CLOSED"


def test_existing_data_provider_wraps_existing_endpoints() -> None:
    provider = ExistingDataProvider(_market_quote, _market_history)
    quote = provider.quote("RELIANCE")
    history = provider.history("RELIANCE")
    assert quote["symbol"] == "RELIANCE"
    assert history["symbol"] == "RELIANCE"
    assert quote["go_live_allowed"] is False
    assert history["go_live_allowed"] is False


def test_stale_data_block_payload_is_fail_closed() -> None:
    payload = stale_data_block_payload("RELIANCE", {"state": "STALE", "blockedReasons": ("MARKET_DATA_STALE",), "missingData": False})
    assert payload["blocked"] is True
    assert payload["decision"] == "DATA_UNAVAILABLE"
    assert payload["go_live_allowed"] is False


def test_live_order_submit_still_blocked() -> None:
    result = _live_order_submit({"preview_id": "missing", "typed_confirmation": "CONFIRM_LIVE_ORDER", "approval_mode": True})
    assert result["status"] == "BLOCKED"
    assert result["broker_order_id"] is None
    assert result["go_live_allowed"] is False
