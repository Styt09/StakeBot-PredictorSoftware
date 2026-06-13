.PHONY: test check compile run-local init-db export-audit-json

test:
	pytest -q

check:
	git diff --check

compile:
	python -m compileall -q src tests

run-local:
	ALPHA_GATE_PROFILE=LOCAL TRADING_MODE=PAPER_TRADING python scripts/run_local.py

init-db:
	python scripts/init_db.py

export-audit-json:
	python scripts/export_audit_json.py
