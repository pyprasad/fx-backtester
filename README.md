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

## Final USDJPY Research Baseline

The human-confirmed final research baseline after FX-2H is:

- Strategy: `FX Swing Trend Reclaim v1`
- Market and direction: `USDJPY`, short only
- Selected guardrail: `min_risk_3pips`
- Weekend policy: `force_close_friday_20_30`
- Status: historical research only; not production-ready or live-trading approved

The versioned strategy information contract is
[`config/strategies/usdjpy_fx_swing_trend_reclaim_v1_final.yaml`](config/strategies/usdjpy_fx_swing_trend_reclaim_v1_final.yaml).
The documentation package starts at
[`docs/strategies/README.md`](docs/strategies/README.md). The next phase is FX-2I Demo-Readiness
Gate; no live trading or broker order placement is included.

## Fixed £0.04 Stake Backtest

The fixed-stake DEMO-preparation mode preserves final strategy signals and execution logic while
converting pip outcomes at a constant `£0.04` per pip:

```bash
PYTHONPATH=. .venv/bin/python -m src.main backtest \
  --config config/strategy.usdjpy.fx_swing_trend_reclaim.fixed_004.yaml
```

The fixed config directly embeds the final `force_close_friday_20_30` policy so the command cannot
fall back to the runtime config's research comparison policy. It writes fixed-stake, pip, and
baseline-comparison reports. See
[`docs/demo/usdjpy_fixed_004_demo_plan.md`](docs/demo/usdjpy_fixed_004_demo_plan.md). This mode is
backtest-only and places no IG DEMO or live orders.

Every fixed-stake run also writes `weekend_exposure_audit.csv` and validates the final baseline.
`strategy_summary.csv/json` include the effective config hash, weekend policy, selected guardrail,
weekend crossing counts, and `validation_status`. Failed weekend/P&L checks or a baseline lifecycle
mismatch mark the run `FAILED_VALIDATION`.

## FX-2I: IG DEMO Integration Foundation

FX-2I adds DEMO-only REST authentication, account and USDJPY market discovery, market-rule
extraction, modern Lightstreamer `PRICE`/optional `CHART:TICK` capture, local DEMO tick storage,
dry-run SELL payload validation, and readiness reporting.

Copy `.env.demo.example` to the gitignored `.env.demo` and add credentials locally. The loader
rejects LIVE mode, enabled order execution, disabled dry-run mode, and deprecated `MARKET`
subscriptions. The REST client deliberately has no create-order method.

Start with:

```bash
PYTHONPATH=. .venv/bin/python -m src.main ig-demo-auth-check --env-file .env.demo
```

The currently identified IG DEMO USDJPY DFB candidate is:

```dotenv
IG_MARKET_EPIC=CS.D.USDJPY.TODAY.IP
```

Verify its detailed market rules during normal market hours:

```bash
PYTHONPATH=. .venv/bin/python -m src.main ig-demo-market-rules \
  --env-file .env.demo \
  --epic CS.D.USDJPY.TODAY.IP
```

Then verify modern `PRICE` streaming and capture DEMO ticks:

```bash
PYTHONPATH=. .venv/bin/python -m src.main ig-demo-stream-prices \
  --env-file .env.demo \
  --epic CS.D.USDJPY.TODAY.IP \
  --duration-seconds 120
```

`marketStatus: EDITS_ONLY` does not permit opening new positions and must remain `NOT_READY`;
verify that it changes to `TRADEABLE` during market hours. Search results may display scaled prices
such as `16018`; confirm detailed market metadata and streamed decimal scaling before calculating
spreads or validating dry-run payloads. For the observed `16018 / 16025` quote, configure
`IG_PRICE_SCALE_DIVISOR=100` only after confirming the scale; this normalizes it to
`160.18 / 160.25`, a wide 7-pip spread that the strategy should reject.
Start modern `PRICE` streaming with the divisor blank. If it rejects an unconfirmed scaled FX
price and the raw quote matches the verified integer-like format, set `IG_PRICE_SCALE_DIVISOR=100`
in `.env.demo` and rerun the stream command. Do not apply the divisor when `PRICE` already returns
decimal quotes such as `160.18 / 160.25`.

Full setup and command sequencing are documented in
[`docs/broker/ig_demo_integration.md`](docs/broker/ig_demo_integration.md). The maximum possible
FX-2I readiness is `READY_FOR_DEMO_DRY_RUN`; this phase sends no demo or live orders.

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

## FX-2G: Broker-Realistic Guardrails + Overnight Funding

FX-2G adds configurable research guardrails without changing the selected EMA/RSI/ATR strategy
logic or replacing the baseline. It tests IG-like minimum stop/take-profit distances, minimum
initial risk, spread-to-risk limits, abnormal entry spread, and a `21:30 Europe/London` entry
cutoff before the `22:00` funding boundary. The selected `force_close_friday_20_30` policy remains
enforced.

Funding is a configurable pip-cost model, not a live IG rate feed. It records daily UK `22:00`
crossings and Wednesday triple rollover exposure. Raw backtest P&L remains unchanged; separate
funding-adjusted reports show the modeled effect. Swing mode allows overnight holding by default;
the optional intraday mode can close positions at `21:55`.

Run the recommended research candidate first:

```bash
PYTHONPATH=. .venv/bin/python -m src.main --log-level INFO broker-guardrails \
  --strategy-config config/strategy.usdjpy.fx_swing_trend_reclaim.yaml \
  --guardrail-variants-config config/broker_guardrail_variants.usdjpy.yaml \
  --normalised-tick-path data/normalised_ticks/USDJPY_2022_2025.parquet \
  --candle-path data/candles/USDJPY_2022_2025 \
  --report-output-path reports/broker_guardrails \
  --daily-funding-pips 0.1 \
  --variant recommended_research_guardrail
```

Remove `--variant recommended_research_guardrail` to run all 12 comparison variants. Outputs
include `broker_guardrail_comparison.csv/json`, `broker_guardrail_report.html`, per-variant
backtest reports and rejection logs, plus `funding_adjusted_trade_log.csv`, `funding_events.csv`,
and `funding_summary.csv`.

Signal-time checks reject known-invalid proposals and funding-cutoff entries. A second check uses
the next executable bid/ask tick, actual entry spread, configured slippage, and actual entry-to-stop
distance before execution. The default funding cost is zero; supply `--daily-funding-pips` for a
meaningful cost scenario. FX-2G remains historical research and a passing result does not establish
demo or production readiness.

## FX-2H: Final Guardrail Candidate Bake-Off

FX-2H compares the three surviving FX-2G candidates side by side without changing strategy
parameters or automatically changing the research baseline:

- `ig_min_stop_only`
- `min_risk_3pips`
- `recommended_research_guardrail`

The bake-off combines base and funding-adjusted metrics, broker guardrail statistics, stability,
walk-forward, Monte Carlo, and execution-stress results. It applies configured hard failures before
a weighted score. When scores are within five points, tie-breakers prefer better worst-trade R,
lower drawdown, higher profit factor, and then the simpler guardrail. Human confirmation is always
required.

Run the full bake-off while reusing the completed FX-2G backtests:

```bash
PYTHONPATH=. .venv/bin/python -m src.main --log-level INFO final-guardrail-bakeoff \
  --strategy-config config/strategy.usdjpy.fx_swing_trend_reclaim.yaml \
  --bakeoff-config config/final_guardrail_bakeoff.usdjpy.yaml \
  --guardrail-variants-config config/broker_guardrail_variants.usdjpy.yaml \
  --normalised-tick-path data/normalised_ticks/USDJPY_2022_2025.parquet \
  --candle-path data/candles/USDJPY_2022_2025 \
  --report-output-path reports/final_guardrail_bakeoff \
  --existing-guardrail-run-path reports/broker_guardrails/<completed_fx_2g_run> \
  --reuse-existing true \
  --run-missing-validations true \
  --monte-carlo-iterations 5000
```

Use `--quick true` for 500-iteration Monte Carlo validation. Use
`--run-missing-validations false` for a fast reuse-only report; missing stability, walk-forward, or
stress layers will force `HUMAN_REVIEW`. A later run can reuse candidate-specific validation
outputs with `--existing-bakeoff-run-path`.

Outputs include `candidate_metric_matrix.csv`, `candidate_score_breakdown.csv`,
`candidate_ranking.csv`, `final_candidate_recommendation.json`,
`final_guardrail_bakeoff_summary.csv/json`, chart files, and
`final_guardrail_bakeoff_report.html`. Hard failures include unacceptable worst trade, drawdown,
profit factor, return, Monte Carlo loss/drawdown probability, or execution-stress tail loss.

FX-2H selects only a proposed next research baseline. It remains historical research and does not
make the strategy demo-ready or production-ready.

### FX-2H Final Decision

After human review of the complete 5,000-iteration bake-off, `min_risk_3pips` was selected as the
final research baseline. `ig_min_stop_only` remains the backup. The more conservative
`recommended_research_guardrail` was not selected because its return sacrifice did not materially
improve execution-stress failures or the worst stressed trade. This decision does not authorize
demo or live execution.
