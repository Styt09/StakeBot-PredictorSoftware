"""Export a safe evidence pack JSON to stdout."""
from institutional_trading_platform.runtime import ProductionRuntimeConfig, SQLiteAuditStore, DashboardSummaryService, ShadowRunValidator, EvidencePackGenerator

config = ProductionRuntimeConfig.from_env()
store = SQLiteAuditStore(config.audit_db_path)
pack = EvidencePackGenerator(store, DashboardSummaryService(store), ShadowRunValidator(store)).generate(config_summary=config.__dict__)
print(pack.to_json())
