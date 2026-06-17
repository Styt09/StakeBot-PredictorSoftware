"""Safe environment configuration for ALPHA-GATE X.

Additive config foundation. It never enables live trading by default.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import os
from typing import Any, Mapping


class TradingMode(str, Enum):
    READ_ONLY = "READ_ONLY"
    PAPER = "PAPER"
    SHADOW = "SHADOW"
    LIVE_DISABLED = "LIVE_DISABLED"
    LIVE_ENABLED = "LIVE_ENABLED"


@dataclass(frozen=True)
class RiskLimits:
    maxDailyLoss: float = 1000.0
    maxTradeLoss: float = 250.0
    maxOpenPositions: int = 2
    maxQtyPerOrder: int = 1
    minSignalConfidence: float = 70.0
    minRiskReward: float = 1.5


@dataclass(frozen=True)
class TradingConfig:
    appEnv: str
    tradingMode: TradingMode
    requestedTradingMode: str
    liveTradingEnabled: bool
    marketTimezone: str
    logLevel: str
    riskLimits: RiskLimits
    brokerConfigured: bool
    databaseConfigured: bool
    redisConfigured: bool
    warnings: tuple[str, ...]
    goLiveAllowed: bool = False


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _float(value: str | None, default: float) -> float:
    try:
        return default if value in (None, "") else float(value)
    except ValueError:
        return default


def _int(value: str | None, default: int) -> int:
    try:
        return default if value in (None, "") else int(float(value))
    except ValueError:
        return default


def maskSecret(value: str | None) -> str:
    if value is None:
        return ""
    text = str(value)
    if not text:
        return ""
    if len(text) <= 8:
        return "****"
    return f"{text[:4]}****{text[-3:]}"


def _is_sensitive_name(name: str) -> bool:
    upper = name.upper()
    return any(marker in upper for marker in ("TOKEN", "SECRET", "PASSWORD", "KEY")) or upper in {"DATABASE_URL", "REDIS_URL"}


def maskConfigForLogs(config: Mapping[str, Any]) -> dict[str, Any]:
    masked: dict[str, Any] = {}
    for key, value in config.items():
        if isinstance(value, Mapping):
            masked[key] = maskConfigForLogs(value)
        elif _is_sensitive_name(key):
            masked[key] = maskSecret("" if value is None else str(value))
        else:
            masked[key] = value
    return masked


def _risk_limits(env: Mapping[str, str]) -> RiskLimits:
    return RiskLimits(
        maxDailyLoss=max(0.0, _float(env.get("MAX_DAILY_LOSS"), 1000.0)),
        maxTradeLoss=max(0.0, _float(env.get("MAX_TRADE_LOSS"), 250.0)),
        maxOpenPositions=max(0, _int(env.get("MAX_OPEN_POSITIONS"), 2)),
        maxQtyPerOrder=max(0, _int(env.get("MAX_QTY_PER_ORDER"), 1)),
        minSignalConfidence=max(0.0, min(100.0, _float(env.get("MIN_SIGNAL_CONFIDENCE"), 70.0))),
        minRiskReward=max(0.0, _float(env.get("MIN_RISK_REWARD"), 1.5)),
    )


def validateEnv(env: Mapping[str, str] | None = None) -> tuple[TradingConfig, tuple[str, ...]]:
    values = os.environ if env is None else env
    warnings: list[str] = []
    requested = (values.get("TRADING_MODE") or "PAPER").strip().upper()
    try:
        mode = TradingMode(requested)
    except ValueError:
        warnings.append("INVALID_TRADING_MODE; falling back to PAPER")
        mode = TradingMode.PAPER

    live_requested = _bool(values.get("ENABLE_LIVE_TRADING"), False)
    broker_configured = bool(values.get("ZERODHA_API_KEY") and values.get("ZERODHA_API_SECRET") and values.get("ZERODHA_ACCESS_TOKEN") and values.get("ZERODHA_USER_ID"))
    database_configured = bool(values.get("DATABASE_URL"))
    redis_configured = bool(values.get("REDIS_URL"))

    if mode == TradingMode.LIVE_ENABLED and not live_requested:
        warnings.append("LIVE_ENABLED requested but ENABLE_LIVE_TRADING=false; forcing LIVE_DISABLED")
        mode = TradingMode.LIVE_DISABLED
    if mode == TradingMode.LIVE_ENABLED and not broker_configured:
        warnings.append("LIVE_ENABLED requested but broker config incomplete; forcing LIVE_DISABLED")
        mode = TradingMode.LIVE_DISABLED
    if mode == TradingMode.LIVE_ENABLED and not database_configured:
        warnings.append("LIVE_ENABLED requested but DATABASE_URL missing; forcing LIVE_DISABLED")
        mode = TradingMode.LIVE_DISABLED

    config = TradingConfig(
        appEnv=(values.get("APP_ENV") or "development").strip() or "development",
        tradingMode=mode,
        requestedTradingMode=requested,
        liveTradingEnabled=live_requested and mode == TradingMode.LIVE_ENABLED,
        marketTimezone=(values.get("MARKET_TIMEZONE") or "Asia/Kolkata").strip() or "Asia/Kolkata",
        logLevel=(values.get("LOG_LEVEL") or "info").strip().lower() or "info",
        riskLimits=_risk_limits(values),
        brokerConfigured=broker_configured,
        databaseConfigured=database_configured,
        redisConfigured=redis_configured,
        warnings=tuple(warnings),
        goLiveAllowed=False,
    )
    return config, config.warnings


def getTradingConfig(env: Mapping[str, str] | None = None) -> TradingConfig:
    return validateEnv(env)[0]


def getSafePublicConfig(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    config = getTradingConfig(env)
    return {
        "appEnv": config.appEnv,
        "tradingMode": config.tradingMode.value,
        "liveTradingEnabled": config.liveTradingEnabled,
        "marketTimezone": config.marketTimezone,
        "riskLimits": asdict(config.riskLimits),
        "brokerConfigured": config.brokerConfigured,
        "databaseConfigured": config.databaseConfigured,
        "go_live_allowed": False,
    }


def isLiveTradingEnabled(env: Mapping[str, str] | None = None) -> bool:
    return getTradingConfig(env).liveTradingEnabled


def getTradingMode(env: Mapping[str, str] | None = None) -> str:
    return getTradingConfig(env).tradingMode.value


def startupLogConfig(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    config = getTradingConfig(env)
    return maskConfigForLogs({
        "APP_ENV": config.appEnv,
        "TRADING_MODE": config.tradingMode.value,
        "ENABLE_LIVE_TRADING": config.liveTradingEnabled,
        "brokerConfigured": config.brokerConfigured,
        "databaseConfigured": config.databaseConfigured,
        "redisConfigured": config.redisConfigured,
        "riskLimits": asdict(config.riskLimits),
        "warnings": config.warnings,
        "go_live_allowed": False,
    })
