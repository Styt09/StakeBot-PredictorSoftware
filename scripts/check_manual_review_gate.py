"""Check manual-review gate; never authorizes LIVE_AUTO."""
from institutional_trading_platform.runtime import ProductionRuntimeConfig, SQLiteAuditStore, ShadowRunValidator, ManualReviewGate

config = ProductionRuntimeConfig.from_env()
store = SQLiteAuditStore(config.audit_db_path)
result = ManualReviewGate().evaluate(ShadowRunValidator(store).status(), None, runbook_followed=False)
print({"decision": result.decision.value, "go_live_allowed": result.go_live_allowed, "failures": result.failure_reasons})
