#!/usr/bin/env bash
set -u

ROOT_DIR="${ROOT_DIR:-$(pwd)}"
SAVE_SCRIPT="${SAVE_SCRIPT:-${ROOT_DIR}/scripts/save_shadow_evidence.sh}"
SAVE_TIME_IST="${SAVE_TIME_IST:-15:45}"
LOG_DIR="${LOG_DIR:-${ROOT_DIR}/shadow_evidence/_scheduler_logs}"
mkdir -p "$LOG_DIR"

if [ ! -f "$SAVE_SCRIPT" ]; then
  echo "❌ save script not found: $SAVE_SCRIPT" >&2
  exit 1
fi
chmod +x "$SAVE_SCRIPT"

echo "✅ Daily evidence scheduler started"
echo "Save time IST: $SAVE_TIME_IST"
echo "Save script: $SAVE_SCRIPT"
echo "Log dir: $LOG_DIR"
echo "Note: Codespace/server must be running at save time."

while true; do
  today="$(TZ=Asia/Kolkata date +%Y-%m-%d)"
  now_hm="$(TZ=Asia/Kolkata date +%H:%M)"
  marker="${LOG_DIR}/${today}.done"
  log_file="${LOG_DIR}/${today}.log"

  if [[ "$now_hm" > "$SAVE_TIME_IST" || "$now_hm" == "$SAVE_TIME_IST" ]]; then
    if [ ! -f "$marker" ]; then
      echo "[$(date -Iseconds)] Saving daily evidence for $today" | tee -a "$log_file"
      if ROOT_DIR="$ROOT_DIR" "$SAVE_SCRIPT" >> "$log_file" 2>&1; then
        echo "[$(date -Iseconds)] SAVE_OK" | tee -a "$log_file"
        date -Iseconds > "$marker"
      else
        echo "[$(date -Iseconds)] SAVE_FAILED" | tee -a "$log_file"
      fi
    fi
  fi

  sleep 60
done
