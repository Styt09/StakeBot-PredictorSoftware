# KILL SWITCH RUNBOOK

## Verdict

- PAPER: READY CANDIDATE
- SHADOW: READY CANDIDATE
- LIVE: NO-GO
- go_live_allowed=false

## Purpose

The persistent kill switch is the emergency safety stop. When active, it must block new paper, shadow, and future live order decisions.

## Storage path

```text
.alpha_gate_state/kill_switch.json
```

If this file is corrupt or unreadable, the system must fail closed.

## Check status

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

Reset requires exact typed confirmation.

```bash
curl -fsS -X POST "http://127.0.0.1:8080/api/kill-switch/reset" \
  -H "Content-Type: application/json" \
  -d '{"typed_confirmation":"RESET_KILL_SWITCH","reset_by":"operator"}'
echo
```

## Expected active behavior

- `/api/risk/check` should include KILL_SWITCH_ACTIVE.
- `/api/paper/order` should return BLOCKED.
- `/api/shadow/evaluate` should return SHADOW_BLOCKED or BLOCKED.
- Broker mutations remain BLOCKED.
- go_live_allowed=false.

## Incident note

If kill switch is activated during validation, document the reason in the audit log and readiness report before reset.
