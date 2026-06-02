# Deployment Guide

## Local development

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
pytest
```

## Container build

```bash
docker build -t stakebot-predictorsoftware:latest .
docker run --rm stakebot-predictorsoftware:latest pytest
```

## Production controls

1. Store broker and vendor credentials in a managed secret store; never commit secrets.
2. Enable the kill switch before any incident response or reconciliation breach.
3. Deploy database migrations before service rollout.
4. Run data-contract checks before feature materialization.
5. Require human approval for model promotion and live trading enablement.
6. Send audit events to immutable storage and security monitoring.
