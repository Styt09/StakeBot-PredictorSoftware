# INCIDENT RESPONSE PLAN

## Verdict

- PAPER: READY CANDIDATE
- SHADOW: READY CANDIDATE
- LIVE: NO-GO
- go_live_allowed=false

## Incident priorities

1. Protect user funds by keeping live trading blocked.
2. Activate persistent kill switch when safety is uncertain.
3. Preserve audit evidence.
4. Diagnose without exposing credentials.
5. Restore paper/shadow validation only after safety checks pass.

## Immediate response commands

Activate kill switch:

```bash
curl -fsS -X POST "http://127.0.0.1:8080/api/kill-switch/activate" \
  -H "Content-Type: application/json" \
  -d '{"reason":"incident response","activated_by":"operator"}'
echo
```

Check readiness:

```bash
curl -fsS "http://127.0.0.1:8080/api/readiness/gates"
echo
```

Check audit report:

```bash
curl -fsS "http://127.0.0.1:8080/api/audit/report"
echo
```

Confirm live order blocked:

```bash
curl -fsS -X POST "http://127.0.0.1:8080/api/live/order/submit" \
  -H "Content-Type: application/json" \
  -d '{"symbol":"RELIANCE","side":"BUY","quantity":1}'
echo
```

## Incident categories

- Broker token failure.
- Market data unavailable.
- Risk engine blocking unexpectedly.
- Kill switch active.
- Audit log write/read problem.
- Shadow drift.
- UI/server unavailable.

## Recovery rule

Do not reset the kill switch until the root cause is documented and readiness gates are reviewed. Reset requires typed_confirmation=RESET_KILL_SWITCH.

## Live trading rule

LIVE remains NO-GO after every incident until independent review is complete.
