# ALPHA-GATE X Operational Validation Plan

ALPHA-GATE X must graduate through controlled stages.  Live auto trading is not
approved until every control below has objective evidence.

## Stage 1: Backtest validation

- Use only closed candles; never reference future bars.
- Enter on the next eligible candle after a signal.
- Include brokerage, slippage, spread, and rejected-order assumptions.
- Run walk-forward and out-of-sample tests across bullish, bearish, sideways,
  high-volatility, and low-liquidity regimes.
- Minimum report: win rate, profit factor, max drawdown, average win/loss,
  expectancy, Sharpe ratio, number of trades, no-trade percentage, and largest
  losing streak.

## Stage 2: Paper trading

- Run PAPER_TRADING for at least 30 market days.
- Collect at least 100 paper trades before considering broker approval mode.
- Confirm every signal and order has a `correlation_id`.
- Confirm duplicate order prevention, stale-feed detection, risk rejection
  logging, and kill-switch behavior.

## Stage 3: Approval mode

- Require human approval for every order.
- Compare paper fills with Zerodha-observed quotes and order-book conditions.
- Confirm Zerodha authentication, order status polling, postback/WebSocket order
  updates, and position reconciliation.

## Stage 4: Limited LIVE_AUTO dry run

- Enable `TRADING_MODE=LIVE_AUTO` only when `LIVE_TRADING=true` is also set.
- Start with one-share or minimum practical quantities.
- Keep kill switch staffed and monitor broker disconnect handling.
- Stop immediately on any reconciliation break or unexplained order state.

## Go-live safety checklist

- [ ] Paper trading 30 days complete.
- [ ] Minimum 100 trades reviewed.
- [ ] Profit factor above 1.5 in paper/shadow trading.
- [ ] Max drawdown acceptable.
- [ ] Zerodha order confirmation working.
- [ ] Duplicate order guard working.
- [ ] Kill switch working.
- [ ] Broker disconnect handling working.
- [ ] Daily loss limit working.
- [ ] Position reconciliation working.
- [ ] No repainting test passed.
- [ ] No look-ahead bias test passed.
- [ ] Broker/compliance requirements reviewed for the current SEBI framework.
