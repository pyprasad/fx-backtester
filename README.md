# USDJPY Tick Backtester

Research-only Python backtester for validating USDJPY tick data, building candles, generating
FX Swing Trend Reclaim v1 signals, and simulating fills on bid/ask ticks.

The documented strategy logic, historical result, limitations, and next validation requirements
are available in [FX Swing Trend Reclaim v1](docs/fx_swing_trend_reclaim_v1.md).

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
