# USDJPY Tick Backtester

Research-only Python backtester for validating USDJPY tick data, building candles, generating
FX Swing Trend Reclaim v1 signals, and simulating fills on bid/ask ticks.

The documented strategy logic, historical result, limitations, and next validation requirements
are available in [FX Swing Trend Reclaim v1](docs/fx_swing_trend_reclaim_v1.md).

Current successful research configuration:

- Short-only FX Swing Trend Reclaim v1
- Force-close all open positions Friday at `20:30 UTC`
- 2022-2025 historical return: `65.09%`
- Profit factor: `2.0485`
- Maximum drawdown: `1.46%`
- Worst trade: `-2.02R`
- Weekend-held trades: `0`

These are historical research results, not expected future returns.

## Setup

Requires Python 3.11+. Install with:

```bash
python3.11 -m pip install -e ".[dev]"
```

Place CSV files containing `timestamp,bid,ask,mid,bid_vol,ask_vol` in
`data/raw_ticks/USDJPY/`. Timestamps must be timezone-aware UTC values.

## Commands

```bash
python3.11 -m src.main data-quality --config config/data_quality.usdjpy.yaml
python3.11 -m src.main normalise --config config/data_quality.usdjpy.yaml --overwrite
python3.11 -m src.main build-candles --config config/strategy.usdjpy.fx_swing_trend_reclaim.yaml
python3.11 -m src.main backtest --config config/strategy.usdjpy.fx_swing_trend_reclaim.yaml
python3.11 -m src.main all --data-quality-config config/data_quality.usdjpy.yaml --strategy-config config/strategy.usdjpy.fx_swing_trend_reclaim.yaml --overwrite
```

Paths and file patterns can be overridden without editing YAML or copying source data. Example:

```bash
python3.11 -m src.main all \
  --data-quality-config config/data_quality.usdjpy.yaml \
  --strategy-config config/strategy.usdjpy.fx_swing_trend_reclaim.yaml \
  --raw-tick-path /external/usdjpy/ticks \
  --file-pattern 'usdjpy_ticks_202[2-5].csv' \
  --normalised-output-path data/normalised_ticks/USDJPY_2022_2025.parquet \
  --normalised-tick-path data/normalised_ticks/USDJPY_2022_2025.parquet \
  --candle-path data/candles/USDJPY_2022_2025 \
  --quality-report-path reports/data_quality/USDJPY_2022_2025_quality_report.html \
  --quality-summary-path reports/data_quality/USDJPY_2022_2025_quality_summary.csv \
  --report-output-path reports/runs_2022_2025 \
  --overwrite
```

Progress logs are written to stderr. Redirect both logs and output to a file while retaining
terminal output with:

```bash
python3.11 -m src.main all ... 2>&1 | tee reports/runs_2022_2025/pipeline.log
```

Quality reports appear in `reports/data_quality/`; backtest reports appear in timestamped
folders under `reports/runs/`.

USDJPY uses a pip size of `0.01`; `0.001` is a pipette. Mid prices drive candles and indicators
only. Long entries use ask and exits use bid; short entries use bid and exits use ask. Stops and
targets use the same executable side. Sunday-open spreads are explicitly flagged.

Position sizing uses a simplified price-unit exposure model. Exact GBP/JPY pip-value conversion,
richer interactive charts, additional markets, optimization, and live execution are future work.
This software is for historical research and is not trading advice.

## FX-2A: Backtest Integrity Validation + Worst Trade Forensics

FX-2A exists to verify that the engine uses the correct executable bid/ask side, exits on the
first valid stop or target crossing, calculates R consistently, and explains losses beyond the
planned risk. It must be completed before optimisation because optimising an invalid execution
model only makes the invalid result look more convincing.

Run forensics against an existing run:

```bash
python3.11 -m src.main --log-level INFO forensics \
  --strategy-config config/strategy.usdjpy.fx_swing_trend_reclaim.yaml \
  --run-path reports/runs_2022_2025/<run_id> \
  --normalised-tick-path data/normalised_ticks/USDJPY_2022_2025.parquet \
  --candle-path data/candles/USDJPY_2022_2025
```

Reports are written under `<run_path>/forensics/`, including audit CSVs, JSON/HTML summaries, and
bounded tick windows for the 25 worst trades.

- `PASS`: no critical mismatch was detected.
- `WARNING`: execution is technically consistent, but gaps, spreads, or slippage created material risk.
- `FAIL`: bid/ask, signal alignment, stop-path, or R-accounting behavior requires correction.

If the worst trade is gap-related, evaluate weekend-risk controls without changing the historical
finding. If a stop-audit or bid/ask mismatch is found, fix and revalidate the engine before any
strategy optimisation. A forensic pass does not make the strategy production-ready.

## FX-2B: Weekend Risk Policy + Session Safety Validation

FX-2A proved that the `-14.77R` worst trade was a real 205.4-pip weekend gap rather than an
execution defect. FX-2B compares the unchanged strategy under configurable UTC weekend policies
to determine whether tail risk can be reduced without destroying the historical edge.

Run one policy:

```bash
python3.11 -m src.main --log-level INFO backtest \
  --config config/strategy.usdjpy.fx_swing_trend_reclaim.yaml \
  --weekend-policy-name force_close_friday_20_30 \
  --weekend-variants-config config/weekend_policy_variants.usdjpy.yaml \
  --normalised-tick-path data/normalised_ticks/USDJPY_2022_2025.parquet \
  --candle-path data/candles/USDJPY_2022_2025 \
  --report-output-path reports/runs_2022_2025
```

Run all predefined policies:

```bash
python3.11 -m src.main --log-level INFO weekend-policy-compare \
  --strategy-config config/strategy.usdjpy.fx_swing_trend_reclaim.yaml \
  --weekend-variants-config config/weekend_policy_variants.usdjpy.yaml \
  --normalised-tick-path data/normalised_ticks/USDJPY_2022_2025.parquet \
  --candle-path data/candles/USDJPY_2022_2025 \
  --report-output-path reports/weekend_policy_comparison
```

The variants compare baseline holding, Friday entry blocking, three Friday force-close times,
closing only losing trades, keeping only trades above `+1R`, reducing positions by 50%, and
tightening stops before the weekend. All policy decisions use UTC to avoid daylight-saving
ambiguity and are written to `weekend_policy_events.csv`.

`weekend_policy_comparison.html` ranks variants by return after penalties for drawdown, losses
beyond `-2.5R`, and losses beyond `-5R`, with bonuses for profit factor and average R.

- `REJECT`: worst trade below `-5R` or any loss beyond `-5R`.
- `CAUTION`: tail risk remains between `-2.5R` and `-5R`, or performance is insufficient.
- `PASS`: positive return, profit factor at least `1.3`, and worst trade no worse than `-2.5R`.
- `STRONG_PASS`: worst trade no worse than `-2R`, profit factor at least `1.5`, return above
  `20%`, and drawdown below `10%`.

This score is a research ranking, not strategy optimisation or evidence of production readiness.

### FX-2B Result

The highest-ranked weekend variant was `force_close_friday_20_30`. Compared with allowing
weekend holding, it removed all weekend-held positions, improved historical return from `58.63%`
to `65.09%`, reduced maximum drawdown from `3.95%` to `1.46%`, and improved the worst trade from
`-14.77R` to `-2.02R`.

This policy is the current successful research baseline. See
[FX Swing Trend Reclaim v1](docs/fx_swing_trend_reclaim_v1.md) for its full rules, validation
history, results, and limitations.

## FX-2C: Yearly, Monthly, and Regime Stability Validation

FX-2C checks whether the historical result is distributed across time and market regimes before
walk-forward validation. It does not optimise or change the strategy. The recommended input is an
existing `force_close_friday_20_30` run containing `trade_log.csv`, `equity_curve.csv`, and
`strategy_summary.csv`.

```bash
python3.11 -m src.main --log-level INFO stability-validate \
  --strategy-config config/strategy.usdjpy.fx_swing_trend_reclaim.yaml \
  --run-path reports/weekend_policy_comparison/<comparison_run>/force_close_friday_20_30 \
  --candle-path data/candles/USDJPY_2022_2025 \
  --report-output-path reports/stability_validation
```

The command creates yearly, quarterly, monthly, rolling-window, profit-concentration, daily-regime,
regime-performance, stability-score, JSON, CSV, and HTML outputs. Months with no trades are omitted
because the validation measures active trading periods.

- `85-100`: `STRONG_STABILITY`
- `70-84`: `PASS`
- `50-69`: `WARNING`
- Below `50`: `FAIL`

`PASS` means the configured historical stability thresholds were met and the strategy may proceed
to walk-forward validation. `WARNING` or `FAIL` means weak periods, concentration, or regimes must
be investigated first. None of these verdicts means the strategy is production-ready.

## FX-2D: Walk-Forward Validation

FX-2D follows stability validation by treating each test period as unseen out-of-sample data. It
uses the unchanged fixed-parameter `force_close_friday_20_30` baseline trade log. Train periods are
used only for comparison; they do not optimize parameters or influence test-period signals.

```bash
python3.11 -m src.main --log-level INFO walk-forward \
  --strategy-config config/strategy.usdjpy.fx_swing_trend_reclaim.yaml \
  --run-path reports/weekend_policy_comparison/<comparison_run>/force_close_friday_20_30 \
  --candle-path data/candles/USDJPY_2022_2025 \
  --report-output-path reports/walk_forward
```

Anchored windows test each future year after an expanding historical train period. Rolling windows
test repeated 3-month and 6-month future periods after fixed-length train periods. Trades are
assigned using entry timestamps, preventing test trades from leaking into train statistics.

Outputs include anchored and rolling CSVs, aggregate summaries, score JSON/CSV, and
`walk_forward_report.html`. Scores of `85-100` are `STRONG_WALK_FORWARD`, `70-84` are `PASS`,
`50-69` are `WARNING`, and lower scores are `FAIL`. This remains historical research and does not
establish production readiness.

## FX-2E: Parameter Robustness Testing

FX-2E follows walk-forward validation and checks whether the unchanged short-only
`fx_swing_trend_reclaim_v1` strategy remains acceptable under small nearby parameter changes. The
fixed reference uses the `force_close_friday_20_30` weekend policy.

This is robustness testing, not parameter optimisation. It looks for a stable cluster of
acceptable performance and parameter cliffs. A higher-return variant must not automatically
replace the baseline; the baseline remains the reference unless later research explicitly
approves a change.

```bash
python3.11 -m src.main --log-level INFO parameter-robustness \
  --strategy-config config/strategy.usdjpy.fx_swing_trend_reclaim.yaml \
  --normalised-tick-path data/normalised_ticks/USDJPY_2022_2025.parquet \
  --candle-path data/candles/USDJPY_2022_2025 \
  --report-output-path reports/parameter_robustness
```

The command reuses normalised ticks and existing candles, recalculates parameter-dependent
indicators, and runs the baseline, one-factor, selected paired, and local-neighbourhood variants.
The full Cartesian grid is disabled by default. Equivalent effective configurations are executed
once and reused in paired analysis.

Outputs include `robustness_summary.csv/json`, `one_factor_sensitivity.csv`, paired sensitivity
CSVs and heatmaps, `paired_sensitivity_summary.csv`, `local_neighbourhood_summary.csv`,
`robustness_score.csv/json`, per-variant backtest reports, and `robustness_report.html`.

- One-factor `LOW`/`MEDIUM`/`HIGH` shows increasing degradation while still passing; `CLIFF` means
  the nearby variant failed.
- Paired heatmaps show whether acceptable performance forms a broad region rather than a single
  best point.
- `85-100` is `STRONG_ROBUSTNESS`, `70-84` is `PASS`, `50-69` is `WARNING`, and below `50` is
  `FAIL`.
- `PASS` supports proceeding to Monte Carlo and execution stress testing. `WARNING` or `FAIL`
  requires investigation of fragility first.

FX-2E remains historical research only and does not establish production readiness.

## FX-2F: Monte Carlo + Execution Stress Testing

FX-2F follows parameter robustness by testing the unchanged selected baseline against trade
sequence randomness, resampling, missed trades, worse execution, and injected tail losses. It
uses the selected `force_close_friday_20_30` baseline trade log and does not optimise or change
strategy parameters.

Monte Carlo does not predict future returns. In this project it creates alternative paths from
historical trade-level R outcomes:

- Trade shuffle changes order without replacing trades, isolating sequence and drawdown risk.
- Bootstrap samples trades with replacement, allowing different mixes of winners and losers.
- Block bootstrap resamples short trade clusters to preserve some historical dependence.
- Missed-trade tests remove random trades, the best trades, or the worst trades.
- Execution stress deducts approximate R costs for wider spreads, slippage, Friday closes, and
  delayed entries/exits.

Delayed execution currently uses an explicit adverse-slippage approximation of `0.1` pip per
delayed tick. True delayed tick replay is a future enhancement.
Stress paths measure drawdown relative to the running equity peak at each point, which may differ
from the existing backtest summary's drawdown percentage convention.

Run the default 5,000-iteration stress test:

```bash
python3.11 -m src.main --log-level INFO monte-carlo-stress \
  --strategy-config config/strategy.usdjpy.fx_swing_trend_reclaim.yaml \
  --run-path reports/parameter_robustness/<run_id>/variants/baseline_original \
  --normalised-tick-path data/normalised_ticks/USDJPY_2022_2025.parquet \
  --candle-path data/candles/USDJPY_2022_2025 \
  --report-output-path reports/monte_carlo_stress
```

Use `--quick` for a 500-iteration validation run. Outputs include stress summary and score
CSV/JSON files, Monte Carlo distributions and scenario summaries, sequence/execution/slippage/
spread/Friday-close/missed-trade/tail-loss summaries, selected equity paths, optional Plotly
charts, and `stress_report.html`.

Scores of `85-100` are `STRONG_STRESS_RESILIENCE`, `70-84` are `PASS`, `50-69` are `WARNING`,
and lower scores are `FAIL`. A passing result supports proceeding toward demo-readiness gates,
but does not make the strategy production-ready.
