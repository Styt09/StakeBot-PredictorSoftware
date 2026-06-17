# PRODUCTION RUNBOOK

## Safety verdict

- PAPER: READY CANDIDATE
- SHADOW: READY CANDIDATE
- LIVE: NO-GO
- go_live_allowed=false

Use this runbook for safe paper/shadow validation only. Do not enable real broker order placement.

## Start server

```bash
fuser -k 8080/tcp 8081/tcp 8090/tcp || true
pkill -f institutional_trading_platform.web_app || true

set -a
. ./.env
set +a
export PYTHONPATH=$PWD/src

python - <<'PY' > /tmp/alpha_gate_web.log 2>&1 &
from institutional_trading_platform.web_app import run
run(host="0.0.0.0", port=8080)
PY
```

## Check health

```bash
curl -fsS http://127.0.0.1:8080/health
echo
```

## Check Zerodha quote

```bash
curl -fsS "http://127.0.0.1:8080/api/market/quote?symbol=RELIANCE"
echo
```

## Check broker health

```bash
curl -fsS "http://127.0.0.1:8080/api/broker/health"
echo
```

## Check paper status

```bash
curl -fsS "http://127.0.0.1:8080/api/paper/status"
echo
```

## Check shadow status

```bash
curl -fsS "http://127.0.0.1:8080/api/shadow/status"
echo
```

## Check kill switch

```bash
curl -fsS "http://127.0.0.1:8080/api/kill-switch/status"
echo
```

## Activate kill switch

```bash
curl -fsS -X POST "http://127.0.0.1:8080/api/kill-switch/activate" \
  -H "Content-Type: application/json" \
  -d '{"reason":"manual safety stop","activated_by":"operator"}'
echo
```

## Reset kill switch

```bash
curl -fsS -X POST "http://127.0.0.1:8080/api/kill-switch/reset" \
  -H "Content-Type: application/json" \
  -d '{"typed_confirmation":"RESET_KILL_SWITCH","reset_by":"operator"}'
echo
```

## Check audit report

```bash
curl -fsS "http://127.0.0.1:8080/api/audit/report"
echo
```

## Check readiness gates

```bash
curl -fsS "http://127.0.0.1:8080/api/readiness/gates"
echo
curl -fsS "http://127.0.0.1:8080/api/readiness/go-live-checklist"
echo
```

## Confirm live order still blocked

```bash
curl -fsS -X POST "http://127.0.0.1:8080/api/live/order/submit" \
  -H "Content-Type: application/json" \
  -d '{"symbol":"RELIANCE","side":"BUY","quantity":1}'
echo
```

Expected result: status BLOCKED, broker_order_id null, go_live_allowed=false.

## Secret safety

Do not paste API key, API secret, access token, request token, or user token into logs, tickets, screenshots, or public reports. Rotate any exposed secret immediately.
