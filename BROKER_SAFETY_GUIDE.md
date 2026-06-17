# BROKER SAFETY GUIDE

## Verdict

- PAPER: READY CANDIDATE
- SHADOW: READY CANDIDATE
- LIVE: NO-GO
- go_live_allowed=false

## Broker policy

Zerodha broker integration is read-only in this release. Broker mutation methods must remain blocked.

## Allowed broker operations

- Broker health check.
- Read-only quote check.
- Sanitized profile/margins/positions status if safely available.

## Blocked broker operations

- place_order
- modify_order
- cancel_order
- exit_position

Every broker mutation response must return:

```json
{
  "status": "BLOCKED",
  "reason": "BROKER_MUTATION_DISABLED",
  "broker_order_id": null,
  "go_live_allowed": false
}
```

## Useful endpoints

```text
GET  /api/broker/health
GET  /api/broker/quote?symbol=RELIANCE
GET  /api/broker/profile/status
GET  /api/broker/margins/status
GET  /api/broker/positions/status
POST /api/broker/order/place
POST /api/broker/order/modify
POST /api/broker/order/cancel
POST /api/broker/position/exit
```

## Secret policy

Never expose API key, API secret, access token, request token, or user token in API responses, screenshots, logs, reports, or support tickets. Rotate any exposed secret.

## Live trading status

LIVE: NO-GO. Broker adapter safety does not approve live trading.
