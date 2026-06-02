# Performance Review

The implemented primitives are deterministic and dependency-light. They are suitable for unit-tested control-plane workflows and low-latency validation but are not a substitute for a production streaming engine.

## Current properties

- Data-contract validation is linear in row count and field count.
- Order-book imbalance is linear in inspected depth.
- Portfolio helpers operate in memory and avoid external dependencies.
- Signal evaluation is constant-time relative to the fixed gate and score lists.

## Future performance work

- Use columnar storage for historical bars and features.
- Use streaming infrastructure for ticks, order books, and order events.
- Add latency histograms for ingestion, signal evaluation, risk validation, and broker routing.
- Add load tests around market open, expiry, and volatility shock scenarios.
