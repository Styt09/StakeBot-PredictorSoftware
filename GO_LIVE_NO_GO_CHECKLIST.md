# GO LIVE NO-GO CHECKLIST

## Required verdict

- PAPER: READY CANDIDATE
- SHADOW: READY CANDIDATE
- LIVE: NO-GO
- go_live_allowed=false

LIVE must remain NO-GO until every item below is completed, documented, tested, and approved.

## Mandatory checklist

| Item | Status |
| --- | --- |
| 30 trading days shadow evidence | NO-GO |
| Zero position drift | NO-GO |
| Broker reconciliation | NO-GO |
| Persistent PostgreSQL/Redis state | NO-GO |
| Durable audit logs verified | NO-GO |
| Kill switch tested | NO-GO |
| Risk limits tested | NO-GO |
| Real broker adapter reviewed | NO-GO |
| Manual approval workflow | NO-GO |
| Deployment monitoring | NO-GO |
| Legal/compliance review | NO-GO |
| Secrets rotated | NO-GO |
| Disaster recovery test | NO-GO |

## Current live verdict

LIVE: NO-GO. go_live_allowed=false.

## Rule

No single checklist item can be skipped. Any missing evidence, unresolved drift, token exposure, monitoring gap, or untested failover keeps LIVE as NO-GO.
