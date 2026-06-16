from institutional_trading_platform.runtime import ProductionRuntimeConfig, SQLiteAuditStore

config = ProductionRuntimeConfig.from_env()
config.assert_valid()
print({"profile": config.profile.value, "mode": config.trading_mode.value, "persistence": SQLiteAuditStore(config.audit_db_path).health()})
