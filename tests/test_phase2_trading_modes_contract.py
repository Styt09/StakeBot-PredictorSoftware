from institutional_trading_platform.safe_config import getSafePublicConfig, getTradingConfig
from institutional_trading_platform.web_app import HTML, _live_order_submit


def test_public_config_safe_shape() -> None:
    public = getSafePublicConfig({
        "APP_ENV": "development",
        "TRADING_MODE": "PAPER",
        "ENABLE_LIVE_TRADING": "false",
        "ZERODHA_API_KEY": "key-placeholder",
        "ZERODHA_API_SECRET": "secret-placeholder",
        "ZERODHA_ACCESS_TOKEN": "token-placeholder",
        "DATABASE_URL": "database-placeholder",
        "REDIS_URL": "redis-placeholder",
    })
    text = str(public)
    assert public["tradingMode"] == "PAPER"
    assert public["liveTradingEnabled"] is False
    assert public["go_live_allowed"] is False
    assert "secret-placeholder" not in text
    assert "token-placeholder" not in text
    assert "database-placeholder" not in text
    assert "redis-placeholder" not in text


def test_trading_mode_default_is_paper() -> None:
    config = getTradingConfig({})
    assert config.requestedTradingMode == "PAPER"
    assert config.tradingMode.value == "PAPER"
    assert config.liveTradingEnabled is False
    assert config.goLiveAllowed is False


def test_invalid_mode_falls_back_safely() -> None:
    config = getTradingConfig({"TRADING_MODE": "INVALID"})
    assert config.tradingMode.value == "PAPER"
    assert config.liveTradingEnabled is False
    assert config.warnings


def test_live_enabled_becomes_live_disabled_when_unsafe() -> None:
    config = getTradingConfig({"TRADING_MODE": "LIVE_ENABLED", "ENABLE_LIVE_TRADING": "false"})
    assert config.tradingMode.value == "LIVE_DISABLED"
    assert config.liveTradingEnabled is False


def test_existing_dashboard_contract_still_present() -> None:
    assert "ALPHA-GATE X SHADOW TRADING PLATFORM" in HTML
    assert "Live Market Dashboard" in HTML
    assert "Paper Trading Terminal" in HTML


def test_real_live_order_submit_remains_blocked() -> None:
    result = _live_order_submit({"preview_id": "missing", "typed_confirmation": "CONFIRM_LIVE_ORDER", "approval_mode": True})
    assert result["status"] == "BLOCKED"
    assert result["broker_order_id"] is None
    assert result["go_live_allowed"] is False
