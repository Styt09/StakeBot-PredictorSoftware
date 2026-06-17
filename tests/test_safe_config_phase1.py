from institutional_trading_platform.safe_config import (
    getSafePublicConfig,
    getTradingConfig,
    getTradingMode,
    isLiveTradingEnabled,
    maskConfigForLogs,
    maskSecret,
)


def test_default_mode_is_paper() -> None:
    config = getTradingConfig({})
    assert config.tradingMode.value == "PAPER"
    assert config.liveTradingEnabled is False
    assert config.goLiveAllowed is False


def test_live_enabled_blocked_when_enable_live_false() -> None:
    config = getTradingConfig({"TRADING_MODE": "LIVE_ENABLED", "ENABLE_LIVE_TRADING": "false"})
    assert config.tradingMode.value == "LIVE_DISABLED"
    assert config.liveTradingEnabled is False
    assert any("ENABLE_LIVE_TRADING=false" in reason for reason in config.warnings)


def test_live_enabled_blocked_when_broker_credentials_missing() -> None:
    env = {"TRADING_MODE": "LIVE_ENABLED", "ENABLE_LIVE_TRADING": "true", "DATABASE_URL": "db-url-placeholder"}
    config = getTradingConfig(env)
    assert config.tradingMode.value == "LIVE_DISABLED"
    assert config.liveTradingEnabled is False
    assert config.brokerConfigured is False


def test_missing_broker_credentials_allow_paper_mode() -> None:
    config = getTradingConfig({"TRADING_MODE": "PAPER"})
    assert config.tradingMode.value == "PAPER"
    assert config.brokerConfigured is False
    assert config.liveTradingEnabled is False


def test_secret_masking() -> None:
    assert maskSecret("") == ""
    assert maskSecret("abc") == "****"
    assert maskSecret("abcd1234xyz") == "abcd****xyz"
    masked = maskConfigForLogs({"ANY_SECRET": "abcd1234xyz", "NORMAL": "ok", "DATABASE_URL": "db-url-placeholder"})
    assert masked["ANY_SECRET"] == "abcd****xyz"
    assert masked["DATABASE_URL"] != "db-url-placeholder"
    assert masked["NORMAL"] == "ok"


def test_public_config_does_not_expose_private_values() -> None:
    env = {
        "APP_ENV": "development",
        "TRADING_MODE": "PAPER",
        "ZERODHA_API_KEY": "key-placeholder",
        "ZERODHA_API_SECRET": "secret-placeholder",
        "ZERODHA_ACCESS_TOKEN": "token-placeholder",
        "DATABASE_URL": "db-url-placeholder",
        "REDIS_URL": "redis-url-placeholder",
    }
    public = getSafePublicConfig(env)
    text = str(public)
    assert "secret-placeholder" not in text
    assert "token-placeholder" not in text
    assert "db-url-placeholder" not in text
    assert "redis-url-placeholder" not in text
    assert public["liveTradingEnabled"] is False


def test_invalid_mode_falls_back_safely() -> None:
    config = getTradingConfig({"TRADING_MODE": "DANGER"})
    assert config.tradingMode.value == "PAPER"
    assert config.liveTradingEnabled is False


def test_risk_config_values_parse_correctly() -> None:
    public = getSafePublicConfig({
        "MAX_DAILY_LOSS": "1500",
        "MAX_TRADE_LOSS": "300",
        "MAX_OPEN_POSITIONS": "4",
        "MAX_QTY_PER_ORDER": "2",
        "MIN_SIGNAL_CONFIDENCE": "80",
        "MIN_RISK_REWARD": "2.25",
    })
    risk = public["riskLimits"]
    assert risk["maxDailyLoss"] == 1500.0
    assert risk["maxTradeLoss"] == 300.0
    assert risk["maxOpenPositions"] == 4
    assert risk["maxQtyPerOrder"] == 2
    assert risk["minSignalConfidence"] == 80.0
    assert risk["minRiskReward"] == 2.25


def test_helpers_return_safe_values() -> None:
    assert getTradingMode({}) == "PAPER"
    assert isLiveTradingEnabled({}) is False
