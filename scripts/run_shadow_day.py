"""Safe read-only shadow-day bootstrap script."""
from institutional_trading_platform.runtime import ProductionRuntimeConfig, SQLiteAuditStore, DashboardSummaryService, ShadowRunValidator

config = ProductionRuntimeConfig.from_env()
store = SQLiteAuditStore(config.audit_db_path)
print({"profile": config.profile.value, "valid": config.valid, "shadow": ShadowRunValidator(store).status().recommendation.value, "dashboard": DashboardSummaryService(store).summary().go_live_allowed})
