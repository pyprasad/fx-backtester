# USDJPY Signal Rules

## Required Inputs

Closed 1H signal candles, the latest available closed 4H trend candle, EMA20/50/200, RSI14, ATR14,
session labels, and signal-candle spread. Indicators and candles use mid prices.

## Short Signal

A signal is eligible only when all conditions hold:

1. Latest available 4H close is below 4H EMA200.
2. 1H close is below 1H EMA50.
3. 1H close is within `1.2 x ATR14` of EMA20 or EMA50.
4. RSI14 is below 50 and below its previous 1H value.
5. Signal candle closes below its open.
6. Signal belongs to London morning (`07:00-11:30`) or London/New York overlap (`13:00-16:30`).
7. Signal spread is no greater than `2.0` pips.
8. Weekend and broker-time guards allow a new entry.

No long signal is allowed in this baseline. The closed signal candle must never be followed by an
entry before its close timestamp. The entry instruction is market-on-next-available-tick.

## Initial Proposal

For a short:

- Stop = maximum of signal high and `signal close + 1.2 x ATR14`.
- Proposed target = `signal close - 4 x proposed risk`.

Signal-time guardrail checks are provisional. The mandatory final risk check uses the next
executable bid after configured slippage.

## Rejections

Every rejected candidate must record a machine-readable reason. Relevant reasons include outside
session, spread too high, weekend block, broker minimum distance, below selected 3-pip risk,
funding-time cutoff, and duplicate/open-position constraints.
