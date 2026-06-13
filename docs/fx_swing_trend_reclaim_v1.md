# FX Swing Trend Reclaim v1

## Status

FX Swing Trend Reclaim v1 is a research-only USDJPY strategy that produced a positive historical
backtest result across the available 2022-2025 tick data.

The current successful research configuration is:

- Strategy: `fx_swing_trend_reclaim_v1`
- Direction: short only
- Weekend policy: `force_close_friday_20_30`
- Friday close time: `20:30 UTC`
- Weekend positions allowed: no

FX-2A confirmed that the engine's bid/ask execution, barrier handling, signal alignment, and R
accounting were internally consistent. FX-2B found that force-closing positions at Friday
20:30 UTC removed the observed weekend tail risk while improving the historical result.

The strategy is not proven to be profitable in future markets. The current result should be
treated as a promising research candidate that requires further robustness testing.

## Strategy In Plain English

The strategy looks for opportunities to sell USDJPY when:

1. USDJPY is already in a long-term downtrend.
2. Price temporarily moves upward toward recent moving averages.
3. The temporary recovery loses momentum.
4. Price begins moving downward again.

It accepts frequent small losses while attempting to capture fewer, larger downward moves.

The current version only opens short trades. It does not open long trades.

## Signal Rules

### Long-Term Trend

The latest four-hour candle must close below the four-hour EMA 200.

This prevents the strategy from selling unless the broader market is already in a downtrend.

### Entry-Timeframe Trend

The latest one-hour candle must close below the one-hour EMA 50.

### Pullback

The one-hour price must move near either:

- EMA 20
- EMA 50

The distance from the moving average must be no greater than `1.2 x ATR`.

### Downward Confirmation

The one-hour signal candle must:

- Close below its open.
- Have RSI 14 below 50.
- Have RSI 14 falling compared with the previous candle.

### Entry Filters

New trades are allowed only during these Europe/London session windows:

- London morning: `07:00-11:30`
- London/New York overlap: `13:00-16:30`

The signal candle's average spread must not exceed `2.0` pips. Sunday-open entries are avoided.

## Entry Execution

The strategy enters on the first available tick after the one-hour signal candle closes.

Because the strategy opens short positions:

- Entry uses the bid price.
- Stop-loss, take-profit, trailing-stop, and final exits use the ask price.

Mid prices are used only for candles, indicators, and signal decisions. They are never used for
trade fills.

Configured slippage is `0.002` price units, equal to `0.2` USDJPY pips.

## Risk Management

- Starting research balance: `GBP 10,000`
- Risk per trade: `0.25%` of the current balance
- Maximum simultaneous trades: `1`
- Maximum simultaneous USDJPY trades: `1`
- Maximum configured trade duration: `7 days`
- No martingale
- No averaging down
- No grid trading

Position sizing currently uses a simplified price-unit exposure model. Exact GBP/JPY pip-value
conversion has not yet been implemented.

## Stop-Loss

The initial short stop is placed above the signal price using the greater of:

- The signal candle high.
- `1.2 x ATR` above the signal close.

This attempts to place the stop beyond recent price movement and market volatility.

## Profit Management

`R` means the amount initially risked on a trade.

For example, when the initial risk is GBP 25:

- `1R` = GBP 25
- `2R` = GBP 50
- `4R` = GBP 100

The strategy manages profitable trades as follows:

1. Move the stop to breakeven after approximately `1.2R`.
2. Close 50% of the position after approximately `2R`.
3. Trail the remaining position using `1.5 x ATR`.
4. Use approximately `4R` as the final target.

## Validated Weekend Safety Policy

The successful research configuration force-closes any open position on Friday at the first
available tick at or after `20:30 UTC`.

For short positions, the Friday close uses the ask price. If no suitable tick exists at or after
the configured time, the engine uses the last available Friday tick and records that fallback.

This policy was selected because it:

- Removed all weekend-held trades.
- Removed the observed `-14.77R` weekend-gap loss.
- Reduced maximum drawdown.
- Increased historical return and profit factor.
- Produced the highest safety-adjusted score among the tested weekend variants.

The nearby `20:00 UTC` and `21:00 UTC` force-close variants also performed strongly. This reduces
the risk that the result depends on exactly one selected minute.

## Successful 2022-2025 Backtest Result

Data range:

- Start: `2022-01-02 22:00:05 UTC`
- End: `2025-12-31 21:58:58 UTC`
- Tick count: `158,063,266`

Result:

| Metric | Result |
| --- | ---: |
| Starting balance | GBP 10,000.00 |
| Ending balance | GBP 16,509.10 |
| Total return | 65.09% |
| Total trades | 450 |
| Winning trades | 189 |
| Losing trades | 261 |
| Win rate | 42.00% |
| Profit factor | 2.0485 |
| Average trade | +0.4490R |
| Average winner | +2.0724R |
| Average loser | -0.7266R |
| Best trade | +9.20R |
| Worst trade | -2.0171R |
| Maximum drawdown | 1.46% |
| Maximum consecutive losses | 9 |
| Weekend force closes | 12 |
| Weekend-held trades | 0 |
| Weekend-held losses | 0 |

The strategy was profitable despite losing more trades than it won because its average winner
was materially larger than its average loser.

### Exit Breakdown

| Exit reason | Trades |
| --- | ---: |
| Initial stop-loss | 173 |
| Final take-profit | 76 |
| Trailing stop | 189 |
| Friday weekend force close | 12 |

## Baseline Versus Successful Policy

| Metric | Weekend Allowed Baseline | Friday 20:30 UTC Force Close |
| --- | ---: | ---: |
| Ending balance | GBP 15,862.80 | GBP 16,509.10 |
| Total return | 58.63% | 65.09% |
| Profit factor | 1.8527 | 2.0485 |
| Maximum drawdown | 3.95% | 1.46% |
| Worst trade | -14.77R | -2.02R |
| Weekend-held trades | 12 | 0 |
| Weekend-held losses | 7 | 0 |

The original baseline's worst trade was a real short-position weekend gap of approximately
`205.4` pips against the position. The stop had not crossed before Friday market closure, and
the engine correctly exited on the first available Sunday tick. The Friday force-close policy
removes this specific exposure by closing before the market becomes unavailable.

## Important Caveats

The headline result must not be treated as production-ready.

### Residual Gap And Slippage Risk

The Friday policy removes weekend holding but cannot guarantee that losses remain within `-1R`.
Intraday gaps, spread spikes, and slippage can still cause losses beyond the intended stop.
The successful configuration's worst observed trade was approximately `-2.02R`.

### Extreme Spreads

- Average entry spread: `0.612` pips
- Average exit spread: `1.255` pips
- 27 trades exited with spreads above `2` pips
- 13 trades exited with spreads above `5` pips

One unusually profitable trade exited during a `26.2` pip spread event. Extreme-spread behavior
must be reviewed before relying on the headline result.

### Very Tight Stops

Some generated stops were unusually close to the entry price. The lowest 1% of stop distances
were below approximately `0.75` pips. This can create unrealistic position sizes and unusually
large R-multiples.

### Current Model Limitations

- Position sizing does not yet use exact GBP/JPY pip-value conversion.
- No commissions, financing, or overnight swap charges are included.
- No broker-specific minimum stop distance is enforced.
- The strategy has not been tested on unseen out-of-sample data after 2025.
- The strategy has not been tested with live or paper-trading execution.

## Required Validation Before The Next Phase

Before considering paper trading or production execution:

1. Add and test a configurable minimum stop distance.
2. Add exact account-currency pip-value conversion.
3. Add commissions, swap, and configurable adverse slippage.
4. Add execution-quality reporting for extreme entry and exit spreads.
5. Run walk-forward and unseen out-of-sample testing.
6. Confirm results using an independent tick-data source.
7. Test the validated weekend policy in a paper-trading environment before any production work.

## Reproducing The Result

The strategy configuration is:

`config/strategy.usdjpy.fx_swing_trend_reclaim.yaml`

The successful weekend-policy comparison was generated in:

`reports/weekend_policy_comparison/20260613_000428_usdjpy_fx_swing_trend_reclaim_v1/`

Run the successful research configuration with:

```bash
python3.11 -m src.main --log-level INFO backtest \
  --config config/strategy.usdjpy.fx_swing_trend_reclaim.yaml \
  --weekend-policy-name force_close_friday_20_30 \
  --weekend-variants-config config/weekend_policy_variants.usdjpy.yaml \
  --normalised-tick-path data/normalised_ticks/USDJPY_2022_2025.parquet \
  --candle-path data/candles/USDJPY_2022_2025 \
  --report-output-path reports/runs_2022_2025
```

## Research Warning

Historical profitability does not guarantee future profitability. This strategy and backtester
are intended for research only and are not financial advice.
