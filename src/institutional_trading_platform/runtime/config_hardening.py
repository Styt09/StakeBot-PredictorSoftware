"""Production configuration profiles and fail-closed validation for Phase 9."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from os import environ
from pathlib import Path

from ..alpha_gate_x import TradingMode


class ConfigProfile(StrEnum):
    LOCAL = "LOCAL"
    PAPER = "PAPER"
    SHADOW = "SHADOW"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    SAFE_RECOVERY = "SAFE_RECOVERY"


@dataclass(frozen=True)
class ProductionRuntimeConfig:
    """Environment-backed config that never defaults to live trading."""

    profile: ConfigProfile
    trading_mode: TradingMode
    audit_db_path: str
    zerodha_api_key: str = ""
    zerodha_access_token: str = ""
    valid: bool = True
    failure_reasons: tuple[str, ...] = ()

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "ProductionRuntimeConfig":
        env = env or dict(environ)
        reasons: list[str] = []
        try:
            profile = ConfigProfile(env.get("ALPHA_GATE_PROFILE", ConfigProfile.LOCAL.value).upper())
        except ValueError:
            profile = ConfigProfile.SAFE_RECOVERY
            reasons.append("invalid ALPHA_GATE_PROFILE")
        raw_mode = env.get("TRADING_MODE", TradingMode.PAPER_TRADING.value).upper()
        if raw_mode == TradingMode.LIVE_AUTO.value:
            reasons.append("LIVE_AUTO is rejected by production hardening")
            trading_mode = TradingMode.PAPER_TRADING
        else:
            try:
                trading_mode = TradingMode(raw_mode)
            except ValueError:
                trading_mode = TradingMode.PAPER_TRADING
                reasons.append("invalid TRADING_MODE")
        if profile == ConfigProfile.APPROVAL_REQUIRED:
            trading_mode = TradingMode.APPROVAL_REQUIRED
        if profile == ConfigProfile.SAFE_RECOVERY:
            trading_mode = TradingMode.PAPER_TRADING
        audit_db_path = env.get("AUDIT_DB_PATH", "./alpha_gate_x_audit.db").strip()
        if not audit_db_path:
            reasons.append("AUDIT_DB_PATH is required")
            audit_db_path = "./alpha_gate_x_audit.db"
        if profile in {ConfigProfile.SHADOW, ConfigProfile.APPROVAL_REQUIRED} and not env.get("ZERODHA_API_KEY"):
            reasons.append("ZERODHA_API_KEY is required for SHADOW/APPROVAL_REQUIRED")
        if profile == ConfigProfile.APPROVAL_REQUIRED and not env.get("ZERODHA_ACCESS_TOKEN"):
            reasons.append("ZERODHA_ACCESS_TOKEN is required for APPROVAL_REQUIRED")
        try:
            Path(audit_db_path).parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            reasons.append(f"audit db path unavailable: {exc}")
        return cls(profile, trading_mode, audit_db_path, env.get("ZERODHA_API_KEY", ""), env.get("ZERODHA_ACCESS_TOKEN", ""), not reasons, tuple(reasons))

    def assert_valid(self) -> None:
        if not self.valid:
            raise ValueError("invalid production config: " + "; ".join(self.failure_reasons))
