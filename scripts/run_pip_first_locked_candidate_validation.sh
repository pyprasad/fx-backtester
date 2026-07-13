#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"
STARTING_BALANCE="${STARTING_BALANCE:-28400}"
ITERATIONS="${ITERATIONS:-5000}"
SEED="${SEED:-42}"
OUTPUT_ROOT="${OUTPUT_ROOT:-reports/pip_first_locked_candidate}"

COMMON_CONFIG="config/strategy.usdjpy.fx_swing_trend_reclaim.yaml"
TICK_PATH="data/normalised_ticks/USDJPY_2021_2026.parquet"
CANDLE_PATH="data/candles/USDJPY_2021_2026"

PYTHONPATH=. "$PYTHON_BIN" -m src.main backtest \
  --config "$COMMON_CONFIG" \
  --normalised-tick-path "$TICK_PATH" \
  --candle-path "$CANDLE_PATH" \
  --entry-short-enabled false \
  --entry-long-enabled true \
  --max-trade-duration-days 1 \
  --weekend-policy-name force_close_friday_20_30 \
  --report-output-path "$OUTPUT_ROOT/long_only"

LONG_RUN="$(ls -td "$OUTPUT_ROOT"/long_only/* | head -1)"

PYTHONPATH=. "$PYTHON_BIN" -m src.main pip-first-report \
  --run-path "$LONG_RUN" \
  --starting-balance "$STARTING_BALANCE" \
  --pip-values 0.5,1,2,5 \
  --report-output-path "$OUTPUT_ROOT/comparison"

PYTHONPATH=. "$PYTHON_BIN" -m src.main pip-first-stress \
  --run-path "$LONG_RUN" \
  --starting-balance "$STARTING_BALANCE" \
  --pip-values 0.5,1,2,5 \
  --iterations "$ITERATIONS" \
  --seed "$SEED" \
  --slippage-pips 0,0.2,0.5,1 \
  --missed-trade-rates 0,0.05,0.1,0.2 \
  --report-output-path "$OUTPUT_ROOT/stress"

PYTHONPATH=. "$PYTHON_BIN" -m src.main pip-first-decision \
  --comparison-summary "$OUTPUT_ROOT/comparison/pip_first_summary.csv" \
  --stress-summary "$OUTPUT_ROOT/stress/pip_first_stress_summary.csv" \
  --report-output-path "$OUTPUT_ROOT/decision"

printf '\nLocked pip-first candidate validation complete.\n'
printf 'Run path: %s\n' "$LONG_RUN"
printf 'Decision summary: %s\n' "$OUTPUT_ROOT/decision/pip_first_decision_summary.csv"
