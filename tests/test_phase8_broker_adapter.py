from institutional_trading_platform.broker_adapter import (
    BlockedBrokerMutationAdapter,
    BrokerCredentials,
    ZerodhaReadOnlyAdapter,
)
from institutional_trading_platform.web_app import _live_order_submit


SECRET_TEXT = "verysecret-token-value"


def _quote_provider(symbol: str):
    return {
        "symbol": symbol,
        "ltp": 100.0,
        "validation_status": "VALIDATED",
        "access_token": SECRET_TEXT,
        "api_secret": SECRET_TEXT,
        "go_live_allowed": False,
    }


def test_broker_health_returns_required_fields() -> None:
    adapter = ZerodhaReadOnlyAdapter(
        credentials=BrokerCredentials(api_key="abc123", access_token="tok123", user_id="TTS544"),
        quote_provider=_quote_provider,
    )
    health = adapter.health()
    for key in ["broker", "connected", "read_only", "mutation_enabled", "status", "latency_ms", "last_checked_at", "masked_user_id", "go_live_allowed"]:
        assert key in health
    assert health["broker"] == "ZERODHA"
    assert health["read_only"] is True
    assert health["mutation_enabled"] is False
    assert health["go_live_allowed"] is False


def test_broker_quote_does_not_expose_secrets() -> None:
    adapter = ZerodhaReadOnlyAdapter(
        credentials=BrokerCredentials(api_key="abc123", access_token="tok123", user_id="TTS544"),
        quote_provider=_quote_provider,
    )
    quote = adapter.quote("RELIANCE")
    text = str(quote)
    assert SECRET_TEXT not in text
    assert quote["go_live_allowed"] is False
    assert quote["mutation_enabled"] is False


def test_missing_token_returns_safely() -> None:
    adapter = ZerodhaReadOnlyAdapter(credentials=BrokerCredentials(api_key="abc123", access_token=""), quote_provider=_quote_provider)
    health = adapter.health()
    quote = adapter.quote("RELIANCE")
    assert health["status"] == "TOKEN_MISSING"
    assert quote["status"] == "TOKEN_MISSING"
    assert quote["go_live_allowed"] is False


def test_missing_config_returns_safely() -> None:
    adapter = ZerodhaReadOnlyAdapter(credentials=BrokerCredentials(api_key="", access_token="tok123"), quote_provider=_quote_provider)
    assert adapter.health()["status"] == "CONFIG_MISSING"
    assert adapter.quote("RELIANCE")["status"] == "CONFIG_MISSING"


def test_expired_token_does_not_crash() -> None:
    def bad_quote(symbol: str):
        raise RuntimeError("Token is invalid or has expired")

    adapter = ZerodhaReadOnlyAdapter(credentials=BrokerCredentials(api_key="abc123", access_token="tok123"), quote_provider=bad_quote)
    health = adapter.health()
    quote = adapter.quote("RELIANCE")
    assert health["status"] in {"TOKEN_EXPIRED", "BROKER_UNAVAILABLE"}
    assert quote["status"] == "TOKEN_EXPIRED"


def test_read_only_quote_works_safely() -> None:
    adapter = ZerodhaReadOnlyAdapter(credentials=BrokerCredentials(api_key="abc123", access_token="tok123"), quote_provider=_quote_provider)
    quote = adapter.quote("RELIANCE")
    assert quote["symbol"] == "RELIANCE"
    assert quote["ltp"] == 100.0
    assert quote["read_only"] is True
    assert quote["go_live_allowed"] is False


def test_broker_mutations_are_blocked() -> None:
    blocker = BlockedBrokerMutationAdapter()
    for method in [blocker.place_order, blocker.modify_order, blocker.cancel_order, blocker.exit_position]:
        result = method({"symbol": "RELIANCE"})
        assert result["status"] == "BLOCKED"
        assert result["reason"] == "BROKER_MUTATION_DISABLED"
        assert result["broker_order_id"] is None
        assert result["go_live_allowed"] is False


def test_status_read_endpoints_are_sanitized_or_unavailable() -> None:
    adapter = ZerodhaReadOnlyAdapter(credentials=BrokerCredentials(api_key="abc123", access_token="tok123"))
    assert adapter.profile_status()["status"] == "BROKER_UNAVAILABLE"
    assert adapter.margins_status()["status"] == "BROKER_UNAVAILABLE"
    assert adapter.positions_status()["status"] == "BROKER_UNAVAILABLE"


def test_live_order_submit_remains_blocked() -> None:
    result = _live_order_submit({"preview_id": "missing", "typed_confirmation": "CONFIRM_LIVE_ORDER", "approval_mode": True})
    assert result["status"] == "BLOCKED"
    assert result["broker_order_id"] is None
    assert result["go_live_allowed"] is False
