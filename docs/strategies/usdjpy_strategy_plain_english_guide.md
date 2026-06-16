# USDJPY Strategy Plain-English Guide

This document explains the selected USDJPY strategy in practical language so it is easier to operate,
debug, and extend later.

## One-Sentence Summary

The strategy looks for USDJPY short trades when the bigger 4-hour trend is weak, the 1-hour chart
pulls back into that downtrend, momentum turns down again, and the live broker price is still cheap
enough to trade after spread and risk checks.

## What Market It Trades

- Market: USDJPY
- Broker target: IG
- Direction: short only
- Product currently used in DEMO: `CS.D.USDJPY.TODAY.IP`
- Pip size: `0.01`

Short only means the strategy sells USDJPY. It does not currently take long/buy trades.

## Timeframes

The strategy uses three levels of data:

- 4H trend frame: decides whether the market is generally weak enough to consider shorts.
- 1H signal frame: decides whether there is an actual entry signal.
- Tick execution frame: uses the latest streamed bid/ask price to validate and place the order.

In live DEMO, the bot fetches IG 1H historical candles. It then derives the 4H trend candles locally
from those 1H candles using fixed UTC anchors:

```text
00:00, 04:00, 08:00, 12:00, 16:00, 20:00 UTC
```

This is important because it matches the backtest candle grid. The bot does not use IG's direct
`HOUR_4` candles for signal generation because IG anchors those differently.

## Trading Sessions

The strict DEMO contract allows entries only in these sessions:

- Tokyo: `09:00-18:00 Asia/Tokyo`
- London morning: `07:00-11:30 Europe/London`
- London/New York overlap: `13:00-16:30 Europe/London`

The candle timestamps stay in UTC. Session checks convert the timestamp into the local session
timezone. That means London daylight saving is handled by the timezone conversion, not by changing
the candle anchors.

## Signal Logic

A short signal needs all of these conditions:

- 4H close is below the 200 EMA.
- 1H close is below the 50 EMA.
- Price has pulled back near the 20 EMA or 50 EMA.
- RSI14 is below 50.
- RSI14 is falling compared with the previous candle.
- The 1H candle is bearish, meaning it closes below where it opened.
- The signal happens inside an allowed session.
- Spread is not too high.
- Broker execution guardrails accept the proposed stop/target distances.

If any of those checks fail, there is no trade.

## Entry Timing

The strategy does not enter while a 1H candle is still forming.

It waits for the 1H candle to close. If that closed candle creates a valid signal, the bot uses the
next fresh streamed tick to validate the executable entry price and build the order.

In plain terms:

```text
closed 1H candle creates signal -> latest live tick validates execution -> DEMO order may be placed
```

## Stop Loss And Target

For a short trade:

- Stop is above entry.
- Stop distance uses the larger of signal candle structure and ATR-based risk.
- ATR multiplier: `1.2`
- Final target: `4R`
- Partial take profit: close 50% at `2R`
- Move stop to breakeven after `1.2R`
- Trailing stop uses ATR multiplier `1.5`

The live DEMO order currently sends a market order with stop distance and limit distance. IG confirms
the final `dealReference`, `dealId`, and `dealStatus`.

## Risk And Position Size

Risk per trade is:

```text
0.25% of current account balance
```

The bot asks IG for the active account balance and sizes the trade dynamically. It also respects IG's
minimum deal size and the instrument unit.

Only one USDJPY strategy position is allowed at a time:

```text
max_open_positions = 1
```

If there is already an open USDJPY position, a new signal is blocked.

## Broker Guardrails

The selected strict guardrail is:

```text
min_risk_3pips_spread_ratio_20pct
```

That means:

- Reject initial risk below 3 pips.
- Respect IG minimum stop distance.
- Reject spread above the strategy maximum.
- Reject if spread is more than 20% of the initial risk.
- Reject delayed prices.
- Reject stale prices.
- Reject trades after the configured UK cutoff.
- Reject if market is not tradeable.

In DEMO, IG may require a larger minimum stop than 3 pips. If IG says minimum stop is 6 pips, the bot
uses 6 pips for the actual order risk and sizes the trade from that effective risk.

## Weekend And Funding Rules

The strict strategy contract includes:

- Force close before weekend: Friday `20:30 UTC`.
- Block weekend holding.
- Track overnight funding awareness.
- Apply Wednesday triple rollover awareness in reporting.
- Block new entries after `21:30 Europe/London`.

The current bot work has focused on entry and DEMO order placement. Full live position management
and automatic weekend close handling should be treated as a separate operational milestone before
production use.

## Live Bot Data Flow

The DEMO bot uses two data sources:

- IG historical `HOUR` candles for signal generation.
- IG Lightstreamer `PRICE` ticks for executable entry validation.

The bot keeps only the latest tick in memory and writes audit events instead of storing every tick.

The candle cache lives here:

```text
data/live_cache/ig/usdjpy_hour.parquet
data/live_cache/ig/usdjpy_hour_4.parquet
data/live_cache/ig/usdjpy_metadata.json
```

The 4H file is derived from the 1H file. It is not fetched directly from IG.

To reduce IG REST usage, the bot checks the latest cached 1H candle and requests only the missing
hours plus a small overlap. The metadata shows what it requested:

```json
"request_points": 3,
"missing_hours_estimate": 1,
"overlap_hours": 2
```

## Historical Override Account

For temporary DEMO validation, the bot can use separate `IG_HISTORICAL_*` credentials only for
historical candle reads. Streaming, account balance, positions, orders, and confirms still use the
primary `IG_*` account.

This is useful when the primary account has hit IG historical-data allowance limits. It should remain
a temporary testing mechanism.

## DEMO Order Modes

There are two bot modes.

Monitoring only:

```text
No --confirm PLACE_DEMO_ORDER
```

The bot can find signals and build dry-run payloads, but it cannot submit an order.

Order-enabled DEMO mode:

```text
IG_ORDER_EXECUTION_ENABLED=true
IG_DRY_RUN_ONLY=false
--confirm PLACE_DEMO_ORDER
```

Even in order-enabled mode, the bot only submits if the current signal and all guardrails pass.

## Key Reports

Use these files to understand what happened:

```text
reports/ig_demo_audit/bot_run_usdjpy.json
reports/ig_demo_audit/signal_dry_run_order_usdjpy.json
reports/ig_demo_audit/demo_execution_test.json
reports/ig_demo_audit/open_positions.json
reports/ig_demo_audit/bot_audit_events_usdjpy.jsonl
```

Important statuses:

- `NO_SIGNAL`: latest closed 1H candle had no valid strategy signal.
- `SIGNAL_READY_FOR_DEMO_DRY_RUN`: current signal exists and order payload passed validation.
- `BLOCKED_STALE_CANDLE_CACHE`: historical candles are not current enough to evaluate safely.
- `BLOCKED_BY_GUARDRAIL`: signal exists, but broker/risk/session validation rejected it.

## Before Extending The Strategy

Before changing rules, check these areas:

- Does the change alter the 4H trend filter?
- Does it alter session windows or timezones?
- Does it affect risk per trade or stop distance?
- Does it increase spread sensitivity?
- Does it require long trades as well as shorts?
- Does it require more than one open position?
- Does it require new live position management logic?

After any meaningful strategy change, rerun the validation stack:

- Backtest
- Broker guardrails
- Stability validation
- Walk-forward validation
- Parameter robustness
- Monte Carlo stress
- DEMO dry-run/live-signal checks

Do not promote a change just because one backtest looks better. The selected strategy was chosen
because it survived multiple validation layers, not because it had the highest raw return alone.
