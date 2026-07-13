# USDJPY Strategy Package

This directory contains the integration package for the final agreed historical research baseline:

- Strategy: `fx_swing_trend_reclaim_v1`
- Selected guardrail: `min_risk_3pips_spread_ratio_20pct`
- Market and direction: `USDJPY`, short only
- Weekend policy: `force_close_friday_20_30`
- Status: DEMO validation; not production-ready or live-trading approved

Start with the [Plain-English Strategy Guide](usdjpy_strategy_plain_english_guide.md), then use the
[Final Strategy](usdjpy_fx_swing_trend_reclaim_v1_final_strategy.md) and
[Pipeline Contract](usdjpy_strategy_pipeline_contract.md) for implementation work. The current DEMO
validation contract is
`config/strategies/usdjpy_fx_swing_trend_reclaim_v1_strict_combined_demo.yaml`.

The existing executable research configuration remains
`config/strategy.usdjpy.fx_swing_trend_reclaim.yaml`. The final package does not enable live
execution or automatically modify that runtime configuration.

## Pip-First Research Candidate

The `pip-first-intraday` branch also locked a separate pip-first research candidate for deeper
validation:

- Strategy: `fx_swing_trend_reclaim_v1`
- Market and direction: `USDJPY`, long only
- Sizing research mode: fixed pounds per pip, not dynamic risk sizing
- Status: research candidate only; not production-ready or live-trading approved

Start with [USDJPY Pip-First Long-Only Candidate](usdjpy_pip_first_long_only_candidate.md). The
versioned candidate contract is
`config/strategies/usdjpy_fx_swing_trend_reclaim_v1_pip_first_long_only_candidate.yaml`.
