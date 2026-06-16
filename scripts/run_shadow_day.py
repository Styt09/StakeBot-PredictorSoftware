"""Safe read-only shadow-day readiness check.

This script does not start Zerodha shadow trading.  It exits NO-GO unless all
critical prerequisites are wired by an operator-provided integration layer.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from institutional_trading_platform.alpha_gate_x import assert_real_order_path_forbidden
from institutional_trading_platform.broker import ZerodhaAuthService, ZerodhaConnectionStatus
from institutional_trading_platform.runtime import DashboardSummaryService, ProductionRuntimeConfig, ShadowRunValidator, SQLiteAuditStore

NO_GO = "NO_GO_SHADOW_READINESS"


def main() -> int:
    reasons: list[str] = []
    try:
        assert_real_order_path_forbidden()
    except Exception as exc:  # fail closed; no shadow process starts
        reasons.append(f"live-order path guard failed: {exc}")

    config = ProductionRuntimeConfig.from_env()
    if not config.valid:
        reasons.extend(config.validation_errors)

    store = SQLiteAuditStore(config.audit_db_path)
    health = store.health()
    if health.get("status") != "ok":
        reasons.append("persistence unavailable")

    auth = ZerodhaAuthService().validate()
    if auth.status != ZerodhaConnectionStatus.CONNECTED:
        reasons.extend(auth.reasons or ("Zerodha read-only session unavailable",))

    reasons.append("ZerodhaShadowFeedRunner must be provided by a read-only KiteTicker integration before real shadow")

    if reasons:
        print({"status": NO_GO, "reasons": tuple(reasons), "go_live_allowed": False})
        return 2

    dashboard = DashboardSummaryService(store).summary()
    shadow = ShadowRunValidator(store).status()
    print({"status": "READY_FOR_OPERATOR_DRY_RUN", "profile": config.profile.value, "shadow": shadow.recommendation.value, "dashboard_go_live_allowed": dashboard.go_live_allowed, "go_live_allowed": False})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
