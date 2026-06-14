# USDJPY Fixed £0.04 DEMO Preparation Backtest

## Purpose

The fixed-stake mode models a small IG DEMO spread-bet stake of **£0.04 per pip**. It exists to
make historical backtest P&L directly comparable with later small-size DEMO observations.

The mode is safer for observation because monetary movement is intentionally small and constant.
It does not place DEMO orders and does not make the strategy live-ready.

## Pips And GBP

Ending balance is money, not pips. Pips measure market movement; the stake converts that movement
to GBP:

```text
pnl_gbp = pnl_pips * 0.04
```

Examples:

- 10 pips = £0.40
- 50 pips = £2.00
- 100 pips = £4.00

For a short trade, pips are `(entry_bid - exit_ask) / 0.01`. For a long trade, pips are
`(exit_bid - entry_ask) / 0.01`.

## Unchanged Strategy Behaviour

Entry signals, bid/ask execution, stop loss, take profit, partial profit, breakeven, trailing stop,
the `min_risk_3pips` guardrail, the 21:30 UK entry cutoff, and Friday 20:30 force close are
unchanged. Only the conversion from price movement to monetary P&L changes.

The next phase may prepare controlled IG DEMO order placement. This backtest does not enable or
submit orders.

## Correctness Gate

Each run audits every trade for weekend exposure and validates the effective configuration,
`min_risk_3pips`, Friday 20:30 force-close policy, £0.04 stake arithmetic, worst-trade limit, and
ending-balance identity. The run is marked `FAILED_VALIDATION` if a weekend crossing, old gap-loss
signature, P&L mismatch, or final-baseline lifecycle mismatch is found. Only
`validation_status=PASS` is suitable for later DEMO-readiness review.
