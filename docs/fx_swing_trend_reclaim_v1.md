# FX Swing Trend Reclaim v1

## Status

FX Swing Trend Reclaim v1 is a research-only USDJPY strategy that produced a positive historical
backtest result across the available 2022-2025 tick data.

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

## 2022-2025 Backtest Result

Data range:

- Start: `2022-01-02 22:00:05 UTC`
- End: `2025-12-31 21:58:58 UTC`
- Tick count: `158,063,266`

Result:

| Metric | Result |
| --- | ---: |
| Starting balance | GBP 10,000.00 |
| Ending balance | GBP 15,866.27 |
| Total return | 58.66% |
| Total trades | 450 |
| Win rate | 41.33% |
| Profit factor | 1.85 |
| Average trade | +0.4144R |
| Average winner | +2.1186R |
| Average loser | -0.7864R |
| Maximum drawdown | 3.95% |
| Maximum consecutive losses | 9 |

The strategy was profitable despite losing more trades than it won because its average winner
was materially larger than its average loser.

### Exit Breakdown

| Exit reason | Trades |
| --- | ---: |
| Initial stop-loss | 178 |
| Final take-profit | 77 |
| Trailing stop | 195 |

### Performance By Entry Year

| Year | Trades | Net PnL | Average R | Win rate |
| --- | ---: | ---: | ---: | ---: |
| 2022 | 93 | GBP 1,393.11 | 0.5641R | 47.31% |
| 2023 | 108 | GBP 1,126.23 | 0.3525R | 37.96% |
| 2024 | 85 | GBP 1,333.05 | 0.4807R | 37.65% |
| 2025 | 164 | GBP 2,013.88 | 0.3358R | 42.07% |

## Important Caveats

The headline result must not be treated as production-ready.

### Weekend Gap Risk

The worst trade lost `-14.77R`. It was held over a weekend and USDJPY reopened significantly
above the stop. This is realistic gap-through-stop behavior and demonstrates that actual losses
can exceed the planned risk amount.

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
- No explicit Friday-close or weekend-position exit rule is enforced.
- The strategy has not been tested on unseen out-of-sample data after 2025.
- The strategy has not been tested with live or paper-trading execution.

## Required Validation Before The Next Phase

Before considering paper trading or production execution:

1. Add and test a configurable minimum stop distance.
2. Add weekend-risk rules and compare hold-versus-close behavior.
3. Add exact account-currency pip-value conversion.
4. Add commissions, swap, and configurable adverse slippage.
5. Add execution-quality reporting for extreme entry and exit spreads.
6. Run parameter sensitivity tests without selecting only the best result.
7. Run walk-forward and unseen out-of-sample testing.
8. Confirm results using an independent tick-data source.

## Reproducing The Result

The strategy configuration is:

`config/strategy.usdjpy.fx_swing_trend_reclaim.yaml`

The referenced result was generated in:

`reports/runs_2022_2025/20260612_223729_usdjpy_fx_swing_trend_reclaim_v1/`

Run the existing normalized dataset with:

```bash
python3.11 -m src.main --log-level INFO backtest \
  --config config/strategy.usdjpy.fx_swing_trend_reclaim.yaml \
  --normalised-tick-path data/normalised_ticks/USDJPY_2022_2025.parquet \
  --candle-path data/candles/USDJPY_2022_2025 \
  --report-output-path reports/runs_2022_2025
```

## Research Warning

Historical profitability does not guarantee future profitability. This strategy and backtester
are intended for research only and are not financial advice.
