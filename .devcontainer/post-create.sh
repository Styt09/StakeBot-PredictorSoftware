#!/usr/bin/env bash

set -u

ROOT="/workspaces/StakeBot-PredictorSoftware"
cd "$ROOT" 2>/dev/null || cd "$(pwd)"

mkdir -p .codespace-logs data

{
  echo "=== StakeBot Codespace recovery setup ==="
  date -u
  python --version || true
  git status --short || true

  python -m pip install --upgrade pip || true
  python -m pip install -e . || true
  python -m compileall -q src/institutional_trading_platform || true

  echo "Setup completed. Any dependency error is logged but will not block the Codespace from opening."
  echo "Real broker order submission remains disabled."
} 2>&1 | tee .codespace-logs/post-create.log

exit 0
