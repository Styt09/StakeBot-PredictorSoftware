"""Generate today's daily shadow report from durable audit events."""
from datetime import datetime, timezone
from institutional_trading_platform.runtime import ProductionRuntimeConfig, SQLiteAuditStore, DailyShadowReportGenerator

config = ProductionRuntimeConfig.from_env()
store = SQLiteAuditStore(config.audit_db_path)
print(DailyShadowReportGenerator(store).generate(datetime.now(timezone.utc).date()).to_dict())
