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
- FX-2G: broker-realistic execution guardrails and overnight funding awareness.
- FX-2H: final guardrail candidate bake-off.

FX-2E is not optimisation. Do not select or replace the baseline merely because a variant has
higher historical return. Keep the full Cartesian parameter grid disabled by default, reuse
normalised ticks and candles, and enforce `force_close_friday_20_30` for every robustness variant.

FX-2F is also not optimisation. Use the selected baseline trade log, preserve baseline strategy
parameters, use deterministic random seeds, and keep delayed execution clearly labeled as an
R-based approximation until true delayed tick replay is implemented. Do not interpret a stress
pass as production readiness.

FX-2G is not optimisation and must not change EMA/RSI/ATR entry logic. Apply guardrails before
signal acceptance, preserve executable-side tick pricing, and enforce `force_close_friday_20_30`
for every variant. Funding is a configurable pip-cost research model, not live IG data; keep raw
P&L unchanged and report funding-adjusted results separately. Run the recommended variant before
the full comparison, and do not replace the baseline automatically.

FX-2H compares exactly `ig_min_stop_only`, `min_risk_3pips`, and
`recommended_research_guardrail`. Reuse prior backtests and validations where possible, run only
missing layers, apply hard failures before weighted ranking, and use safety-first tie-breakers.
Always require human confirmation and never modify the main strategy config or research baseline
automatically.

## Commands

Run tests from the repository root with:

```bash
PYTHONPATH=. .venv/bin/python -m pytest -q
PYTHONPATH=. .venv/bin/python -m ruff check .
```

Run FX-2E through FX-2H with the commands documented in `README.md`. Generated reports belong
under their phase-specific report folders and are historical research artifacts, not evidence of
production readiness.
