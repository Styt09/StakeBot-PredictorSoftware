# AUDIT EVIDENCE GUIDE

## Verdict

- PAPER: READY CANDIDATE
- SHADOW: READY CANDIDATE
- LIVE: NO-GO
- go_live_allowed=false

## Purpose

Audit evidence records safety decisions, blocked reasons, broker health checks, kill-switch events, paper activity, and shadow activity.

## Storage path

```text
.alpha_gate_state/audit_log.jsonl
```

## Required rules

- One JSON event per line.
- Credential-like fields must be masked before persistence.
- Corrupt lines must be returned as AUDIT_LINE_UNREADABLE.
- broker_order_id must remain null for blocked broker actions.
- go_live_allowed=false always.

## Useful endpoints

```text
GET /api/audit/recent
GET /api/audit/report
GET /api/audit/export
```

## Check recent events

```bash
curl -fsS "http://127.0.0.1:8080/api/audit/recent?limit=100"
echo
```

## Check report

```bash
curl -fsS "http://127.0.0.1:8080/api/audit/report"
echo
```

## Evidence needed before any future live review

- 30 trading days of shadow records.
- Broker health records.
- Risk check records.
- Kill switch test records.
- Broker mutation blocked records.
- Live order blocked records.
- Readiness reports.

LIVE remains NO-GO until evidence is complete and independently reviewed.
