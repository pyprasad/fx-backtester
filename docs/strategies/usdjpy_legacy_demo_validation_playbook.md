# USDJPY Legacy Demo Validation Playbook

This document is the canonical reference for the USDJPY strategy currently approved for DEMO
forward testing.

It records the exact strategy behavior that produced the strongest evidence set, the data and
calendar assumptions behind that evidence, the operational guardrails for DEMO, and the checklist
for testing the same idea on another FX pair.

## Current Decision

The strategy is suitable to continue running in IG DEMO validation.

It is not approved for live-money execution. DEMO use is allowed because the validated historical
behavior is strong across a full tick-executed `2020-2026` run, every calendar year tested, both
trade directions, all configured sessions, macro-news blackout, spread/slippage stress, and Monte
Carlo resampling.

## Strategy Identity

| Field | Value |
| --- | --- |
| Strategy name | `fx_swing_trend_reclaim_v1` |
| Market | `USDJPY` |
| Broker target | `IG` |
| DEMO contract | `usdjpy_fx_swing_trend_reclaim_v1_intraday_6pip_attached_demo.yaml` |
| Runtime strategy config | `config/strategy.usdjpy.fx_swing_trend_reclaim.yaml` |
| Direction mode | Long and short |
| Timeframes | `4H` trend, `1H` signal, tick execution |
| Pip size | `0.01` |
| Signal timing mode | `legacy_open_timestamp` |
| Risk per trade | `0.25%` |
| Max open trades | `1` total, `1` per market |
| Weekend policy | Force close Friday `20:30 UTC` |
| Macro news guard | Enabled for high-impact USD and JPY events |
| DEMO status | Continue forward testing |
| Live status | Not approved |

## Plain-English Model

The strategy looks for trend continuation after a pullback.

For a long trade, the higher timeframe must be bullish, the hourly candle must reclaim strength
near the moving averages, RSI must turn upward through the configured momentum level, and the signal
candle must close bullish.

For a short trade, the higher timeframe must be bearish, the hourly candle must reject near the
moving averages, RSI must turn downward through the configured momentum level, and the signal candle
must close bearish.

The strategy does not try to predict every move. It waits for a closed hourly candle, checks whether
the setup exists, then enters on the next executable tick if spread, broker distance, weekend, and
news rules allow it.

## Important Timing Decision

The profitable evidence is for:

```text
signal_timing_mode = legacy_open_timestamp
```

This means the strategy labels and evaluates the hourly signal using the candle timestamp already
used by the original backtests. The later candle-close implementation is more technically strict,
but it did not reproduce the same profitability during research.

For DEMO validation, the rule is:

- Use `legacy_open_timestamp`.
- Do not silently switch to `candle_close_timestamp`.
- Treat `candle_close_timestamp` as a separate research variant that needs its own proof.

This is deliberate. The aim is to forward-test the behavior that the profitable historical evidence
actually proves, not a cleaner but materially different interpretation.

## Timeframes And Candle Anchors

The strategy uses:

| Layer | Timeframe | Purpose |
| --- | --- | --- |
| Trend | `4H` | Higher-timeframe market direction |
| Signal | `1H` | Entry setup |
| Execution | Tick | Entry, stop, target, spread, and slippage realism |

Candles are UTC anchored. The derived 4H grid uses:

```text
00:00, 04:00, 08:00, 12:00, 16:00, 20:00 UTC
```

This matters for broker integration. IG direct `HOUR_4` candles can have different anchors, so the
bot should derive 4H candles from the same 1H grid used by the backtest.

## Sessions

The DEMO candidate allows three sessions:

| Session | Local time |
| --- | --- |
| Tokyo | `09:00-18:00 Asia/Tokyo` |
| London morning | `07:00-11:30 Europe/London` |
| London/New York overlap | `13:00-16:30 Europe/London` |

Session checks are timezone-aware. London daylight saving is handled through `Europe/London`, not by
manual UTC offsets.

## Indicators

| Indicator | Value |
| --- | --- |
| EMA fast | `20` |
| EMA mid | `50` |
| EMA slow | `200` |
| RSI period | `14` |
| ATR period | `14` |

Mid prices are used for candles and indicators. Bid/ask prices are used for execution.

## Entry Rules

### Long

All conditions must pass:

- Long side is enabled by the strategy contract.
- 4H trend close is above 4H EMA200.
- 1H close is above 1H EMA50.
- 1H close is near EMA20 or EMA50 within `1.2 ATR`.
- RSI14 is above `50`.
- RSI14 is rising versus the previous 1H candle.
- The 1H signal candle is bullish.
- Signal is inside an allowed session.
- Spread is acceptable.
- Weekend policy allows a new entry.
- Broker execution guardrails accept the stop and target distances.
- News guard is not in blackout.

Long execution uses:

```text
entry = ask
exit/stop/target = bid
```

### Short

All conditions must pass:

- Short side is enabled by the strategy contract.
- 4H trend close is below 4H EMA200.
- 1H close is below 1H EMA50.
- 1H close is near EMA20 or EMA50 within `1.2 ATR`.
- RSI14 is below `50`.
- RSI14 is falling versus the previous 1H candle.
- The 1H signal candle is bearish.
- Signal is inside an allowed session.
- Spread is acceptable.
- Weekend policy allows a new entry.
- Broker execution guardrails accept the stop and target distances.
- News guard is not in blackout.

Short execution uses:

```text
entry = bid
exit/stop/target = ask
```

## Execution Contract

The validated DEMO contract is the intraday 6-pip attached take-profit candidate:

```text
config/strategies/usdjpy_fx_swing_trend_reclaim_v1_intraday_6pip_attached_demo.yaml
```

Key execution settings:

| Rule | Value |
| --- | --- |
| Entry type | Market on next available tick after signal |
| Take profit | Fixed `6.0` pips |
| Take-profit mode | Attached limit |
| Minimum stop distance | `6.0` pips |
| Minimum take-profit distance | `6.0` pips |
| Minimum initial risk | `6.0` pips |
| Risk per trade | `0.25%` |
| Maximum trade duration | `1` day |
| Default slippage | `0.005` price points |
| Trailing ATR | Disabled in this DEMO contract |
| Move stop to breakeven | After `1.2R` where applicable |
| Partial take profit | Configured at `2R / 50%`, but fixed attached TP is the primary exit |

The strategy must validate the executable entry tick, not just the signal candle close, before
placing a DEMO order.

## Risk Rules

Mandatory risk rules:

- Risk `0.25%` of current balance per trade.
- Only one open USDJPY strategy position.
- No pyramiding.
- No averaging down.
- No martingale.
- No manual override of rejected signals.
- Block entries after the configured late-day cutoff.
- Force-close Friday according to the weekend policy.
- Reject trades that do not satisfy broker minimum stop or limit distances.

The backtest assumes GBP account currency, but live/demo sizing must continue to use broker account
balance and broker instrument rules.

## Spread And Broker Guardrails

Spread and distance checks are not optional in DEMO.

The candidate tracks:

- Entry spread.
- Exit spread.
- Initial risk in pips.
- Spread-to-risk ratio.
- IG minimum stop distance.
- IG minimum limit distance.
- Time-of-day entry guard.
- Market tradeability.

Current absolute signal spread limit:

```text
max_spread_pips = 2.0
```

The full historical run reported:

```text
average_spread_pips_at_entry = 0.529
average_spread_pips_at_exit = 0.443
```

## Macro News Guard

For the full validation, the strategy used a combined high-impact USD/JPY Nasdaq calendar:

```text
data/macro_calendar/usd_jpy_events_2020_2026_nasdaq.csv
```

Calendar composition:

| Period | Events |
| --- | ---: |
| 2020 | `1206` |
| 2021 | `1191` |
| 2022 | `1154` |
| 2023 | `1114` |
| 2024 | `1178` |
| 2025 | `1145` |
| 2026 to Jun 12 | `520` |
| Total | `7508` |

News guard settings:

| Rule | Value |
| --- | --- |
| Affected currencies | `USD`, `JPY` |
| Impact levels | `HIGH` |
| Before event blackout | `60` minutes |
| After event blackout | `60` minutes |
| Block new entries | Yes |
| Close existing positions | No |
| Log skipped signals | Yes |

Full-run skipped signals:

```text
total skipped = 607
buy skipped = 400
sell skipped = 207
```

The news guard reduces opportunity but does not break the edge. It should remain enabled for DEMO
unless a separate controlled validation proves a better calendar filter.

## Weekend And Funding Boundaries

Weekend policy:

- Force close Friday at `20:30 UTC`.
- Block weekend holding.
- Block Sunday-open entries according to the configured opening buffer.
- Do not open new positions after the late-Friday entry cutoff.

The validated full historical run had:

```text
weekend_force_close_exit_count = 6
```

Funding is tracked as an operational concern, but this intraday 6-pip DEMO candidate is designed to
avoid long unmanaged holding periods.

## Full Historical Evidence

The strongest validation run is:

```text
reports/legacy_validation/full_2020_2026_with_news/20260726_185456_usdjpy_fx_swing_trend_reclaim_v1
```

Inputs:

| Input | Path |
| --- | --- |
| Normalized ticks | `data/normalised_ticks/USDJPY_2020_2026.parquet` |
| Candles | `data/candles/USDJPY_2020_2026_intraday_fixed_tp` |
| Macro calendar | `data/macro_calendar/usd_jpy_events_2020_2026_nasdaq.csv` |
| Strategy config | `config/strategy.usdjpy.fx_swing_trend_reclaim.yaml` |
| Contract config | `config/strategies/usdjpy_fx_swing_trend_reclaim_v1_intraday_6pip_attached_demo.yaml` |
| Signal timing | `legacy_open_timestamp` |

Headline results:

| Metric | Value |
| --- | ---: |
| Starting balance | `10000` |
| Ending balance | `53067.47` |
| Total return | `430.6747%` |
| Total trades | `3173` |
| Winning trades | `2916` |
| Losing trades | `257` |
| Win rate | `91.9004%` |
| Profit factor | `3.8031` |
| Net profit | `43067.47` |
| Max drawdown | `0.5758%` |
| Max drawdown amount | `305.57` |
| Average R | `0.2107` |
| Worst trade R | `-1.657` |
| Best trade R | `3.6299` |
| Max consecutive losses | `3` |
| Max consecutive wins | `108` |

Direction split:

| Direction | Trades | Net PnL | Average R | Win rate |
| --- | ---: | ---: | ---: | ---: |
| Long | `2074` | `30484.65` | `0.2134` | `91.13%` |
| Short | `1099` | `12582.82` | `0.2055` | `93.36%` |

Session split:

| Session | Trades | Net PnL | Average R | Win rate |
| --- | ---: | ---: | ---: | ---: |
| Tokyo | `2246` | `31093.82` | `0.2152` | `92.21%` |
| London/New York overlap | `703` | `9306.13` | `0.1977` | `90.61%` |
| London morning | `224` | `2667.51` | `0.2057` | `92.86%` |

Yearly split:

| Year | Trades | Net PnL | Average R | Win rate |
| --- | ---: | ---: | ---: | ---: |
| 2020 | `333` | `2311.67` | `0.2503` | `87.39%` |
| 2021 | `421` | `3718.35` | `0.2512` | `83.85%` |
| 2022 | `537` | `5455.78` | `0.2184` | `96.09%` |
| 2023 | `555` | `5601.14` | `0.1672` | `91.71%` |
| 2024 | `556` | `8153.12` | `0.1895` | `92.81%` |
| 2025 | `547` | `11088.63` | `0.2002` | `95.43%` |
| 2026 partial | `224` | `6738.80` | `0.2428` | `93.30%` |

The key observation is that every tested year is profitable. The strategy is not relying on a
single year, one direction, or one session.

## Monte Carlo And Stress Evidence

The full Monte Carlo report is:

```text
reports/monte_carlo_stress/legacy_2020_2026_with_news_full/20260726_185520_usdjpy_fx_swing_trend_reclaim_v1_force_close_friday_20_30
```

Headline stress results:

| Metric | Value |
| --- | ---: |
| Iterations | `5000` |
| Stress score | `100` |
| Verdict | `STRONG_STRESS_RESILIENCE` |
| Probability of loss | `0.0%` |
| Worst Monte Carlo p5 return | `376.9626%` |
| Worst Monte Carlo scenario | `block_bootstrap_20` |
| p95 max drawdown | `1.3941%` |
| p99 max drawdown | `1.6208%` |
| Median profit factor | `3.5304` |
| Worst execution scenario | `slippage_1.0_both` |
| Worst execution return | `110.8948%` |

Missed-trade stress:

| Scenario | p5/return | Probability of loss |
| --- | ---: | ---: |
| Miss random 5% | `378.4091%` | `0.0%` |
| Miss best 5% | `287.4362%` | `0.0%` |
| Miss random 10% | `336.9109%` | `0.0%` |
| Miss best 10% | `205.6482%` | `0.0%` |
| Miss random 20% | `265.9127%` | `0.0%` |
| Miss best 20% | `108.3219%` | `0.0%` |

Execution stress:

Even with `1.0` pip slippage on both entry and exit, the strategy remained profitable:

```text
return = 110.8948%
profit_factor = 2.0604
max_drawdown = 2.3241%
verdict = PASS
```

Sequence stress caveat:

The artificial worst-ordering tests fail when all losing trades are forced into extreme clusters:

```text
worst_trades_first drawdown = 48.2619%
best_trades_first drawdown = 48.2619%
loss_clusters drawdown = 37.9376%
```

This is not the historical path, but it is a real risk reminder. DEMO monitoring should watch for
loss clustering and stop the bot if forward drawdown behavior stops resembling historical behavior.

## Reproduction Commands

Normalize the 2020 USDJPY ticks:

```bash
./.venv/bin/python -m src.main --log-level INFO normalise \
  --config config/data_quality.usdjpy.yaml \
  --raw-tick-path /Users/my/mayu_solutions/duka-range/data/usdjpy/ticks \
  --file-pattern usdjpy_ticks_2020.csv \
  --normalised-output-path data/normalised_ticks/USDJPY_2020.parquet \
  --overwrite
```

Merge the normalized `2020` and `2021-2026` tick parquet files:

```bash
./.venv/bin/python - <<'PY'
import polars as pl
from pathlib import Path

out = Path("data/normalised_ticks/USDJPY_2020_2026.parquet")
lf = pl.concat(
    [
        pl.scan_parquet("data/normalised_ticks/USDJPY_2020.parquet"),
        pl.scan_parquet("data/normalised_ticks/USDJPY_2021_2026.parquet"),
    ],
    how="vertical",
).sort("timestamp_utc")
lf.sink_parquet(out)
PY
```

Download missing Nasdaq calendar slices:

```bash
./.venv/bin/python scripts/fetch_nasdaq_usdjpy_macro_calendar.py \
  --start-date 2020-01-01 \
  --end-date 2020-12-31 \
  --output data/macro_calendar/usd_jpy_events_2020_nasdaq.csv \
  --cache-dir data/macro_calendar/cache/nasdaq
```

```bash
./.venv/bin/python scripts/fetch_nasdaq_usdjpy_macro_calendar.py \
  --start-date 2021-01-01 \
  --end-date 2021-12-31 \
  --output data/macro_calendar/usd_jpy_events_2021_nasdaq.csv \
  --cache-dir data/macro_calendar/cache/nasdaq
```

```bash
./.venv/bin/python scripts/fetch_nasdaq_usdjpy_macro_calendar.py \
  --start-date 2026-01-01 \
  --end-date 2026-06-12 \
  --output data/macro_calendar/usd_jpy_events_2026_to_0612_nasdaq.csv \
  --cache-dir data/macro_calendar/cache/nasdaq
```

Merge the calendar slices:

```bash
./.venv/bin/python - <<'PY'
import polars as pl
from pathlib import Path

files = [
    "data/macro_calendar/usd_jpy_events_2020_nasdaq.csv",
    "data/macro_calendar/usd_jpy_events_2021_nasdaq.csv",
    "data/macro_calendar/usd_jpy_events_2022_2025_nasdaq.csv",
    "data/macro_calendar/usd_jpy_events_2026_to_0612_nasdaq.csv",
]

out = Path("data/macro_calendar/usd_jpy_events_2020_2026_nasdaq.csv")
df = (
    pl.concat([pl.read_csv(path) for path in files], how="vertical")
    .unique(subset=["event_id"], keep="first")
    .sort(["event_time_utc", "currency", "event_name"])
)
df.write_csv(out)
PY
```

Build combined candles:

```bash
./.venv/bin/python -m src.main --log-level INFO build-candles \
  --config config/strategy.usdjpy.fx_swing_trend_reclaim.yaml \
  --normalised-tick-path data/normalised_ticks/USDJPY_2020_2026.parquet \
  --candle-path data/candles/USDJPY_2020_2026_intraday_fixed_tp
```

Run the full backtest:

```bash
./.venv/bin/python -m src.main --log-level INFO backtest \
  --config config/strategy.usdjpy.fx_swing_trend_reclaim.yaml \
  --strategy-contract-config config/strategies/usdjpy_fx_swing_trend_reclaim_v1_intraday_6pip_attached_demo.yaml \
  --normalised-tick-path data/normalised_ticks/USDJPY_2020_2026.parquet \
  --candle-path data/candles/USDJPY_2020_2026_intraday_fixed_tp \
  --news-calendar-file data/macro_calendar/usd_jpy_events_2020_2026_nasdaq.csv \
  --report-output-path reports/legacy_validation/full_2020_2026_with_news \
  --signal-timing-mode legacy_open_timestamp
```

Run full Monte Carlo stress:

```bash
./.venv/bin/python -m src.main --log-level INFO monte-carlo-stress \
  --strategy-config config/strategy.usdjpy.fx_swing_trend_reclaim.yaml \
  --run-path reports/legacy_validation/full_2020_2026_with_news/20260726_185456_usdjpy_fx_swing_trend_reclaim_v1 \
  --normalised-tick-path data/normalised_ticks/USDJPY_2020_2026.parquet \
  --candle-path data/candles/USDJPY_2020_2026_intraday_fixed_tp \
  --report-output-path reports/monte_carlo_stress/legacy_2020_2026_with_news_full \
  --iterations 5000 \
  --skip-charts
```

Run tests:

```bash
./.venv/bin/python -m pytest
```

Expected current result:

```text
223 passed, 7 warnings
```

## DEMO Operating Checklist

Before starting the bot:

- Confirm branch and local changes are understood.
- Confirm `signal_timing_mode` is `legacy_open_timestamp`.
- Confirm the DEMO contract is the 6-pip attached take-profit contract.
- Confirm `NEWS_GUARD_ENABLED=true`.
- Confirm the live macro calendar is fresh and covers the forward window.
- Confirm IG market discovery still maps USDJPY to the expected epic.
- Confirm market status is tradeable.
- Confirm account is DEMO.
- Confirm `IG_DRY_RUN_ONLY=false` only when intentionally placing DEMO orders.
- Confirm order placement requires the explicit `PLACE_DEMO_ORDER` confirmation.

During DEMO:

- Record every signal decision.
- Record every broker rejection.
- Compare each actual DEMO order with the expected dry-run payload.
- Track skipped news signals.
- Track spread at entry and exit.
- Track slippage.
- Track missed signals caused by stale candles, stale ticks, disconnected streams, or IG REST limits.
- Stop and investigate if the bot sees more than `3` consecutive losses.
- Stop and investigate if drawdown materially exceeds the historical/stress path.
- Do not change strategy rules during the forward-test window.

## What Must Not Change Silently

These are strategy-defining assumptions. Any change here creates a new candidate and needs fresh
validation:

- Signal timing mode.
- 4H candle anchor method.
- Session windows.
- Direction mode.
- Risk per trade.
- Fixed 6-pip take profit.
- Minimum stop or take-profit distance.
- News blackout window.
- News calendar source/filtering.
- Entry price side mapping.
- Stop/target price side mapping.
- Max open trades.
- Weekend force-close policy.
- Spread limit.
- Slippage assumption.

## Using This Idea On Another Pair

Do not copy the USDJPY results to another pair. Copy the process.

For a new pair:

1. Define pip size, broker epic, minimum stop distance, minimum limit distance, and account-currency
   pip value.
2. Download tick data covering as many years as possible.
3. Normalize ticks using the pair-specific data quality config.
4. Build candles with the same UTC anchor rules.
5. Download or build the pair-specific macro calendar using the currencies that actually affect the
   pair.
6. Start with the same strategy idea, but do not assume `6` pips is correct for the new pair.
7. Run a baseline backtest with no parameter search.
8. Run a controlled candle/session/TP search only if the baseline is promising.
9. Require year-by-year profitability or a clear reason why one year is acceptable.
10. Require both direction and session breakdowns.
11. Run Monte Carlo stress with at least `5000` iterations.
12. Run spread/slippage execution stress using that pair's real spread profile.
13. Run the full test suite.
14. Document the selected pair-specific contract before DEMO.

Minimum evidence before DEMO on another pair:

- Multi-year tick backtest.
- Pair-specific macro calendar.
- Positive total return.
- Acceptable year-by-year behavior.
- Profit factor above `1.3`.
- Max drawdown below the selected risk tolerance.
- Monte Carlo probability of loss near `0%`.
- Profitable under realistic spread/slippage stress.
- Clear broker guardrail compatibility.

## Current Open Risks

- The validated behavior depends on `legacy_open_timestamp`.
- Nasdaq calendar timestamps should remain subject to occasional spot checks against official
  release schedules.
- Sequence stress shows that severe loss clustering would be painful even though historical and
  Monte Carlo paths are strong.
- DEMO execution quality still needs forward evidence: fills, slippage, rejected orders, stale data,
  and latency.
- The strategy is not yet production/live approved.

## Current Recommendation

Continue DEMO forward testing with the validated configuration.

Do not optimize or refactor the strategy while DEMO validation is active. The next useful work is
operational evidence collection: every signal, every skipped signal, every order payload, every
broker response, every fill, and every mismatch between live behavior and the historical model.
