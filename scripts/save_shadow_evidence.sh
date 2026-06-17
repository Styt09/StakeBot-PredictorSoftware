#!/usr/bin/env bash
set -u

BASE_URL="${BASE_URL:-http://127.0.0.1:8080}"
ROOT_DIR="${ROOT_DIR:-$(pwd)}"
DATE_DIR="${EVIDENCE_DATE:-$(TZ=Asia/Kolkata date +%Y-%m-%d)}"
OUT_DIR="${EVIDENCE_DIR:-${ROOT_DIR}/shadow_evidence/${DATE_DIR}}"
mkdir -p "$OUT_DIR"

write_json_fallback() {
  local file="$1"
  local endpoint="$2"
  local reason="$3"
  python - "$file" "$endpoint" "$reason" <<'PY'
import json, sys
from datetime import datetime, timezone
path, endpoint, reason = sys.argv[1:4]
payload = {
    "status": "DATA_UNAVAILABLE",
    "endpoint": endpoint,
    "reason": reason,
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "go_live_allowed": False,
}
with open(path, "w", encoding="utf-8") as f:
    json.dump(payload, f, indent=2)
    f.write("\n")
PY
}

save_get() {
  local endpoint="$1"
  local file="$2"
  if ! curl -fsS "${BASE_URL}${endpoint}" -o "${OUT_DIR}/${file}"; then
    write_json_fallback "${OUT_DIR}/${file}" "$endpoint" "curl_failed"
  fi
}

save_post() {
  local endpoint="$1"
  local file="$2"
  local body="$3"
  if ! curl -fsS -X POST "${BASE_URL}${endpoint}" -H "Content-Type: application/json" -d "$body" -o "${OUT_DIR}/${file}"; then
    write_json_fallback "${OUT_DIR}/${file}" "$endpoint" "curl_failed"
  fi
}

save_get "/health" "health.json"
save_get "/api/readiness/gates" "readiness_gates.json"
save_get "/api/readiness/report" "readiness_report.json"
save_get "/api/readiness/go-live-checklist" "go_live_checklist.json"
save_get "/api/audit/report" "audit_report.json"
save_get "/api/audit/recent?limit=500" "audit_recent.json"
save_get "/api/shadow/status" "shadow_status.json"
save_get "/api/shadow/report" "shadow_report.json"
save_get "/api/broker/health" "broker_health.json"
save_get "/api/kill-switch/status" "kill_switch_status.json"
save_post "/api/live/order/submit" "live_order_block_check.json" '{"symbol":"RELIANCE","side":"BUY","quantity":1}'

python - "$OUT_DIR" "$BASE_URL" <<'PY'
import json, os, sys
from datetime import datetime, timezone
out_dir, base_url = sys.argv[1:3]
files = sorted(x for x in os.listdir(out_dir) if x.endswith('.json'))
manifest = {
    "status": "SAVED",
    "base_url": base_url,
    "saved_at": datetime.now(timezone.utc).isoformat(),
    "evidence_dir": out_dir,
    "files": files,
    "live_trading_enabled": False,
    "go_live_allowed": False,
}
with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as f:
    json.dump(manifest, f, indent=2)
    f.write("\n")
PY

echo "✅ Shadow evidence saved: $OUT_DIR"
ls -la "$OUT_DIR"
