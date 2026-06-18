# USDJPY Validation History

| Phase | Result | Headline finding |
| --- | --- | --- |
| FX-2A Integrity | PASS | Bid/ask execution and R accounting valid; original `-14.77R` was a real weekend gap. |
| FX-2B Weekend policy | PASS | `force_close_friday_20_30` removed weekend holdings and controlled worst trade near `-2.02R`. |
| FX-2C Stability | STRONG_STABILITY | All years profitable; performance distributed across periods and regimes. |
| FX-2D Walk-forward | STRONG_WALK_FORWARD | All anchored test years profitable and nearly all rolling windows profitable. |
| FX-2E Robustness | STRONG_ROBUSTNESS | Nearby parameters remained profitable; baseline was not isolated. |
| FX-2F Stress | PASS | Monte Carlo strong, but tiny-risk trades created execution fragility. |
| FX-2G Guardrails | PASS | Broker distance, minimum risk, time, spread awareness, and funding modeling preserved viability. |
| FX-2H Bake-off | SELECTED_MIN_RISK_3PIPS | Human review selected `min_risk_3pips` as the final research baseline. |
| Next-level ATR15 | DEMO_CANDIDATE | ATR `1.5`, combined Tokyo/London sessions, and lifecycle guardrails returned `174.6211%` over 2021-2026 with `STRONG_STABILITY`, `STRONG_WALK_FORWARD`, and `STRONG_STRESS_RESILIENCE`. |

## FX-2H Decision

`min_risk_3pips` was selected after the complete 5,000-iteration bake-off. It had the highest
candidate profit factor and average R, removed all sub-3-pip trades, retained nearly all baseline
return, and produced no execution-stress or hard failures.

`ig_min_stop_only` remains the backup but permits some sub-3-pip trades and higher maximum
spread/risk exposure. `recommended_research_guardrail` was not selected because its return
sacrifice did not materially improve stressed worst trade or failure count.

## Interpretation Boundary

These validations use historical 2022-2025 data and research assumptions. They do not validate
future profitability, IG order behavior, exact account-currency position sizing, operational
resilience, or real-money safety. The strategy is not production-ready.

The later ATR15 candidate validation used the available 2021-2026 dataset through
`2026-06-12 20:59 UTC`. It strengthens the DEMO validation case but does not change the production
boundary: no live trading is approved from historical validation alone.
