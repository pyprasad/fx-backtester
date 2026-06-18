# USDJPY ATR15 Next-Level Research Candidate

This note records the current next-level USDJPY research candidate selected after extending the
baseline with combined sessions, ATR stop widening, broker guardrails, and grouped-strategy
overlap analysis.

## Candidate

- Base strategy: `fx_swing_trend_reclaim_v1`
- Market and direction: `USDJPY`, short only
- Runtime config base: `config/strategy.usdjpy.fx_swing_trend_reclaim.yaml`
- Demo contract: `config/strategies/usdjpy_fx_swing_trend_reclaim_v1_atr15_combined_candidate.yaml`
- ATR stop multiplier: `1.5`
- Risk per trade: `0.25%`
- Weekend policy: `force_close_friday_20_30`
- Selected guardrail: `min_risk_3pips_spread_ratio_20pct_lifecycle_throttled`
- Sessions:
  - Tokyo, `09:00-18:00 Asia/Tokyo`
  - London morning, `07:00-11:30 Europe/London`
  - London/New York overlap, `13:00-16:30 Europe/London`

This is a DEMO validation candidate only. It is not live-trading approved.

## Extended Validation Result

The candidate was rerun on the available 2021-2026 dataset:

- Tick data range: `2021-01-03 22:00 UTC` to `2026-06-12 20:59 UTC`
- Backtest report: `reports/next_level_validation_2021_2026/backtest/20260618_181314_usdjpy_fx_swing_trend_reclaim_v1`
- Stability report: `reports/next_level_validation_2021_2026/stability/20260618_182407_usdjpy_fx_swing_trend_reclaim_v1_force_close_friday_20_30`
- Walk-forward report: `reports/next_level_validation_2021_2026/walk_forward/20260618_182414_usdjpy_fx_swing_trend_reclaim_v1_force_close_friday_20_30`
- Monte Carlo report: `reports/next_level_validation_2021_2026/monte_carlo/20260618_182420_usdjpy_fx_swing_trend_reclaim_v1_force_close_friday_20_30`

Headline metrics:

| Metric | Value |
| --- | ---: |
| Starting balance | `10000` |
| Ending balance | `27462.11` |
| Total return | `174.6211%` |
| Approx annualized return | `20.42%` |
| Trades | `743` |
| Win rate | `43.7416%` |
| Profit factor | `2.5389` |
| Max drawdown | `1.1028%` |
| Worst trade | `-1.6101R` |
| Stability verdict | `STRONG_STABILITY` |

Yearly return:

| Year | Return |
| --- | ---: |
| 2021 | `18.1998%` |
| 2022 | `17.1368%` |
| 2023 | `20.9267%` |
| 2024 | `16.7795%` |
| 2025 | `37.1189%` |
| 2026 partial | `2.4325%` |

## Cost and Stress Notes

The selected lifecycle guardrail produced:

- Return before funding: `171.1848%`
- Profit factor before funding: `2.5221`
- Max drawdown: `1.1035%`
- Guardrail verdict: `STRONG_GUARDRAIL`

With a `0.2` pip daily funding assumption:

- Return after funding: `170.7522%`
- Profit factor after funding: `2.5157`
- Worst trade after funding: `-1.6384R`

Monte Carlo and execution stress remained strong:

- Stress verdict: `STRONG_STRESS_RESILIENCE`
- P5 return: `132.0008%`
- P1 return: `117.7574%`
- P99 drawdown: `3.8137%`
- Probability of loss: `0%`
- Worst execution scenario: `slippage_1.0_both`, still `116.3555%`

The artificial worst-trades-first sequence still fails with a large drawdown. That scenario is an
extreme sequence-risk warning, not the primary deployment decision metric.

## Interpretation

The extended 2021-2026 validation strengthens the case for DEMO forward validation. The result is
historically robust but remains below the desired `30%` annual return target, with an estimated
annualized return near `20.42%`.

The candidate should be treated as a replacement candidate for the current demo strategy, not an
additive portfolio member. Grouped-strategy research showed high duplicate-entry overlap between
ATR variants and the baseline, so stacking similar variants can amplify correlated losses without
adding much independent edge.

Next research should test session extensions as controlled variants, comparing return, profit
factor, drawdown, spread/risk rejections, and session attribution against this baseline.
