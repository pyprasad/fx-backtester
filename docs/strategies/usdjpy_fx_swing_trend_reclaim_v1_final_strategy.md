# FX Swing Trend Reclaim v1: Final Research Strategy

## Approval Boundary

This is the final agreed USDJPY **historical research baseline** after FX-2H. It is not
production-ready, demo-execution approved, or live-trading approved. The selected broker
guardrail is `min_risk_3pips`.

## Strategy Definition

| Property | Final value |
| --- | --- |
| Market | USDJPY |
| Direction | Short only |
| Broker target | IG |
| Pip size | `0.01` |
| Trend / signal / execution | `4H` / `1H` / tick |
| Source timestamps | UTC |
| Broker time rules | Europe/London |
| Weekend policy | `force_close_friday_20_30` |
| Risk per trade | `0.25%` |
| Maximum open positions | `1` |

The strategy sells a controlled bearish reclaim: the 4H market is below EMA200, the 1H close is
below EMA50 after pulling near EMA20 or EMA50, RSI14 is below 50 and falling, and the signal candle
is bearish. Entry occurs on the next available executable tick after the closed 1H signal candle.

## Execution And Management

- Short entry uses bid; short exits, stops, targets, and trailing exits use ask.
- Mid prices are used for candles, indicators, and signal references only.
- Initial stop is the safer/higher of signal-candle high and `1.2 x ATR` above signal close.
- Reject trades below the IG-style `2` pip stop minimum or selected `3` pip initial-risk minimum.
- Move stop to breakeven at `1.2R`, close 50% at `2R`, trail at `1.5 x ATR`, and target `4R`.
- Do not open after `21:30 Europe/London`; track holdings through `22:00` funding cutoff.
- Force-close Friday at `20:30 UTC`; weekend holding is prohibited.

## Candidate Decision

`min_risk_3pips` was selected because it eliminated sub-3-pip trades while retaining about
`93.78%` of baseline trades and `99.79%` of baseline return. It produced the highest candidate
profit factor (`~2.2246`) and average R (`~0.4768`) with no hard or execution-stress failures.

`ig_min_stop_only` is the backup but remains too permissive. `recommended_research_guardrail` was
not selected because its additional conservatism sacrificed about `8.8` return percentage points
without materially improving worst stressed trade or failure count.

## Source Of Truth

The versioned information contract is
`config/strategies/usdjpy_fx_swing_trend_reclaim_v1_final.yaml`. Runtime behavior is still supplied
by the existing executable config plus the selected weekend and guardrail variants. Any integration
must reconcile both before demo validation.
