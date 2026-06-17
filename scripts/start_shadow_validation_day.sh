#!/usr/bin/env bash
set -u

BASE_URL="${BASE_URL:-http://127.0.0.1:8080}"
SAVE_TIME_IST="${SAVE_TIME_IST:-15:45}"
ROOT_DIR="${ROOT_DIR:-$(pwd)}"
LOG_FILE="${LOG_FILE:-/tmp/shadow_evidence_scheduler.log}"
WEB_LOG="${WEB_LOG:-/tmp/alpha_gate_web.log}"

cd "$ROOT_DIR"

echo "=== START SHADOW VALIDATION DAY ==="
echo "Root: $ROOT_DIR"
echo "Base URL: $BASE_URL"
echo "Evidence save time IST: $SAVE_TIME_IST"

echo "=== STOP OLD SERVER ==="
fuser -k 8080/tcp 8081/tcp 8090/tcp || true
pkill -f institutional_trading_platform.web_app || true

echo "=== LOAD ENV ==="
if [ -f ./.env ]; then
  set -a
  . ./.env
  set +a
else
  echo "⚠️ .env not found; continuing with environment variables only"
fi
export PYTHONPATH="$ROOT_DIR/src"

echo "=== START SERVER ==="
python - <<'PY' > "$WEB_LOG" 2>&1 &
from institutional_trading_platform.web_app import run
run(host="0.0.0.0", port=8080)
PY

sleep 3

echo "=== START EVIDENCE + TRACKER SCHEDULER ==="
pkill -f shadow_validation_daily_scheduler || true
mkdir -p shadow_evidence/_scheduler_logs
nohup bash -c '
exec -a shadow_validation_daily_scheduler bash -c '\''
set -u
while true; do
  now=$(TZ=Asia/Kolkata date +%H:%M)
  today=$(TZ=Asia/Kolkata date +%Y-%m-%d)
  marker="shadow_evidence/_scheduler_logs/${today}.done"
  mkdir -p shadow_evidence/_scheduler_logs

  if [[ "$now" > "'"$SAVE_TIME_IST"'" || "$now" == "'"$SAVE_TIME_IST"'" ]]; then
    if [ ! -f "$marker" ]; then
      echo "[$(date -Iseconds)] Saving shadow evidence + tracker for $today"
      bash scripts/save_shadow_evidence.sh
      python scripts/update_30_day_tracker.py
      date -Iseconds > "$marker"
      echo "[$(date -Iseconds)] SAVE_OK"
    fi
  fi
  sleep 60
done
'\''
' > "$LOG_FILE" 2>&1 &

echo "=== HEALTH CHECK ==="
curl -fsS "$BASE_URL/health"
echo

echo "=== READINESS CHECK ==="
curl -fsS "$BASE_URL/api/readiness/gates"
echo

echo "=== BROKER HEALTH ==="
curl -fsS "$BASE_URL/api/broker/health"
echo

echo "=== KILL SWITCH STATUS ==="
curl -fsS "$BASE_URL/api/kill-switch/status"
echo

echo "=== LIVE ORDER MUST BE BLOCKED ==="
curl -fsS -X POST "$BASE_URL/api/live/order/submit" \
  -H "Content-Type: application/json" \
  -d '{"symbol":"RELIANCE","side":"BUY","quantity":1}'
echo

echo "✅ Shadow validation day started"
echo "✅ Daily evidence + 30-day tracker scheduler started"
echo "❌ Live trading remains NO-GO"
echo "Logs:"
echo "  Web: $WEB_LOG"
echo "  Scheduler: $LOG_FILE"
