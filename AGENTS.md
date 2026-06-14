# Repository Guidance

## Research Scope

- This project is a historical USDJPY tick backtester. Do not add live trading behavior.
- The current research baseline is `fx_swing_trend_reclaim_v1`, `short_only`, with
  `force_close_friday_20_30`.
- Preserve executable-side pricing: short entries use bid and exits use ask; long entries use ask
  and exits use bid. USDJPY pip size is `0.01`.

## Validation Sequence

- FX-2A: execution integrity and worst-trade forensics.
- FX-2B: weekend risk policy selection.
- FX-2C: stability validation.
- FX-2D: walk-forward validation.
- FX-2E: nearby parameter robustness testing.
- FX-2F: Monte Carlo and execution stress testing.

FX-2E is not optimisation. Do not select or replace the baseline merely because a variant has
higher historical return. Keep the full Cartesian parameter grid disabled by default, reuse
normalised ticks and candles, and enforce `force_close_friday_20_30` for every robustness variant.

FX-2F is also not optimisation. Use the selected baseline trade log, preserve baseline strategy
parameters, use deterministic random seeds, and keep delayed execution clearly labeled as an
R-based approximation until true delayed tick replay is implemented. Do not interpret a stress
pass as production readiness.

## Commands

Run tests from the repository root with:

```bash
PYTHONPATH=. .venv/bin/python -m pytest -q
PYTHONPATH=. .venv/bin/python -m ruff check .
```

Run FX-2E and FX-2F with the commands documented in `README.md`. Generated reports belong under
their phase-specific report folders and are historical research artifacts, not evidence of
production readiness.
