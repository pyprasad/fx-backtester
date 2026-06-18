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

The current next-level DEMO research candidate is documented in
[USDJPY ATR15 Next-Level Research Candidate](usdjpy_atr15_next_level_candidate.md). It extends the
baseline with ATR `1.5`, Tokyo plus London sessions, and the
`min_risk_3pips_spread_ratio_20pct_lifecycle_throttled` guardrail. Its 2021-2026 historical
validation remained strong, but it is still DEMO validation only and not live-trading approved.
