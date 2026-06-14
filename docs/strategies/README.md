# USDJPY Strategy Package

This directory contains the integration package for the final agreed historical research baseline:

- Strategy: `fx_swing_trend_reclaim_v1`
- Selected guardrail: `min_risk_3pips`
- Market and direction: `USDJPY`, short only
- Weekend policy: `force_close_friday_20_30`
- Status: historical research only; not production-ready or live-trading approved

Start with [Final Strategy](usdjpy_fx_swing_trend_reclaim_v1_final_strategy.md), then use the
[Pipeline Contract](usdjpy_strategy_pipeline_contract.md) for implementation work. The versioned
configuration contract is
`config/strategies/usdjpy_fx_swing_trend_reclaim_v1_final.yaml`.

The existing executable research configuration remains
`config/strategy.usdjpy.fx_swing_trend_reclaim.yaml`. The final package does not enable live
execution or automatically modify that runtime configuration.
