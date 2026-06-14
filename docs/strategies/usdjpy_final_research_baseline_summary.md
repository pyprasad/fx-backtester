# USDJPY Final Research Baseline Summary

## Final Selection

The final research baseline is `fx_swing_trend_reclaim_v1`, short only, with
`force_close_friday_20_30` and the `min_risk_3pips` guardrail.

Headline FX-2H evidence for `min_risk_3pips`:

| Metric | Result |
| --- | ---: |
| Trades | 422 |
| Return after modeled funding | ~64.86% |
| Profit factor after funding | ~2.2246 |
| Average R after funding | ~0.4768 |
| Maximum drawdown | ~1.51% |
| Worst trade | ~-2.02R |
| Maximum spread/risk | ~18.07% |
| 5,000-iteration Monte Carlo P5 return | ~45.35% |
| Monte Carlo P95 drawdown | ~3.28% |
| Execution-stress failures | 0 |

All years and anchored test years were profitable; rolling walk-forward test windows were 100%
profitable. No hard-fail rule triggered.

## Candidate Disposition

- **Selected:** `min_risk_3pips`, best balance of execution protection and retained edge.
- **Backup:** `ig_min_stop_only`, strong but allows some sub-3-pip risk and higher spread/risk.
- **Not selected:** `recommended_research_guardrail`, too conservative for the current baseline.

This is historical evidence from 2022-2025. It is not a forecast and does not authorize demo or
real-money execution.
