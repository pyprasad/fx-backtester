# USDJPY Execution Rules

## Pricing

- Short entry: next available bid after the closed signal candle.
- Short exit, stop, target, trailing stop, and Friday close: ask.
- Long-side mappings remain ask entry and bid exit for contract completeness, but longs are disabled.
- Mid price must not be used for fills.

Configured research slippage is `0.002` price units (`0.2` USDJPY pips). The executable-entry
guardrail must evaluate risk and spread after applying the configured entry slippage.

## Ordering And Position State

- One open position maximum; reject signals while a position is active.
- No pyramiding, averaging down, martingale, or backtest manual override.
- Entry must be strictly after signal timestamp.
- Maximum trade duration is seven days.
- Friday force close uses the first available tick at or after `20:30 UTC`, with the existing
  last-Friday-tick fallback recorded when required.

## Exit Priority

Use the existing validated engine behavior: process executable-side price movement, breakeven,
partial take profit, ATR trailing stop, stop/target/deadline, weekend policy, and intraday funding
avoidance only when intraday mode is explicitly enabled.

## Audit Requirements

Persist entry/exit timestamps and prices, executable spread, initial/final stop, target history,
trailing history, partial exits, exit reason, MFE/MAE, and policy events. Demo integration must add
broker order IDs, requested versus filled prices, rejection payloads, and latency measurements.
