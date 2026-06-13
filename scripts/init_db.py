from os import environ
from institutional_trading_platform.runtime import SQLiteAuditStore

path = environ.get("AUDIT_DB_PATH", "./alpha_gate_x_audit.db")
store = SQLiteAuditStore(path)
print(store.health())
