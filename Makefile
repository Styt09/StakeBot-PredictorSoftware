.PHONY: test check compile run-local init-db export-audit-json zerodha-profile-smoke zerodha-integration-audit

test:
	pytest -q

check:
	git diff --check
	python scripts/no_live_order_static_scan.py
	python scripts/basic_secret_scan.py
	python scripts/import_smoke.py

compile:
	python -m compileall -q src tests

run-local:
	ALPHA_GATE_PROFILE=LOCAL TRADING_MODE=PAPER_TRADING python scripts/run_local.py

init-db:
	python scripts/init_db.py

export-audit-json:
	python scripts/export_audit_json.py

zerodha-profile-smoke:
	python scripts/zerodha_profile_smoke_test.py

zerodha-integration-audit:
	python scripts/zerodha_integration_audit.py
