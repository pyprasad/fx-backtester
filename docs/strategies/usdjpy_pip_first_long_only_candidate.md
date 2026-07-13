# USDJPY Pip-First Long-Only Candidate

## Status

`fx_swing_trend_reclaim_v1` long-only is locked as the current pip-first research candidate for
deeper validation.

This is not production-ready, not live-trading approved, and does not replace the existing FX-2H
short-only research baseline. It also does not modify `docker-compose.demo.intraday.yml`.

Versioned contract:

```text
config/strategies/usdjpy_fx_swing_trend_reclaim_v1_pip_first_long_only_candidate.yaml
```

## Why This Candidate Was Locked

The pip-first branch compared long-only and long/short over the historical 2021-2026 dataset. The
long/short candidate produced more raw pips, but the long-only candidate had materially lower pip
drawdown and fewer operational fragility flags.

| Candidate | Trades | Net pips | Pip PF | Max pip DD | Decision |
| --- | ---: | ---: | ---: | ---: | --- |
| long-only | 929 | 3,644.1 | 1.6413 | 174.4 | Selected for next validation |
| long/short | 1,307 | 5,000.0 | 1.5227 | 402.9 | Not selected for next validation |

The decision report selected long-only because it had no hard flags. Long/short triggered:

- `MISS_BEST_10_WITH_1PIP_SLIPPAGE_FRAGILE`
- `HIGH_PIP_DRAWDOWN`

## Fixed Pip-Value Interpretation

Historical fixed-size view for long-only:

| Fixed size | Historical net P&L | Historical max drawdown |
| --- | ---: | ---: |
| £0.50/pip | £1,822.05 | £87.20 |
| £1.00/pip | £3,644.10 | £174.40 |
| £2.00/pip | £7,288.20 | £348.80 |
| £5.00/pip | £18,220.50 | £872.00 |

These are historical research translations of pips into pounds. They are not forecasts.

## Stress Findings

Normal adverse stress, using 1 pip slippage and 10% randomly missed trades:

| Candidate | Bootstrap p05 net pips |
| --- | ---: |
| long-only | 843.95 |
| long/short | 1,041.95 |

Miss-best-trades stress, using 1 pip slippage and missing the best 10% of trades:

| Candidate | Net pips |
| --- | ---: |
| long-only | -2,253.75 |
| long/short | -4,343.95 |

This means the candidate must be validated operationally. Missing large winners can damage or
reverse the edge.

## Next Steps

1. Keep this candidate research-only.
2. Run the pip-first validation commands from the README or this document.
3. Review the generated decision summary before any demo configuration change.
4. If validation remains acceptable, build a DEMO-only fixed-size long-only dry-run path.
5. Require explicit human confirmation before any order-enabled demo bot update.

## DEMO Dry-Run Docker Path

The dry-run container for this candidate is:

```text
docker-compose.demo.pip-first-long-only.yml
```

It is configured with:

- `IG_ORDER_EXECUTION_ENABLED=false`
- `IG_DRY_RUN_ONLY=true`
- no `BOT_CONFIRM`
- strategy contract `usdjpy_fx_swing_trend_reclaim_v1_pip_first_long_only_candidate.yaml`
- fixed deal size `0.5`

It should stream IG DEMO prices, refresh historical candles, evaluate long-only signals, and write
dry-run order/audit reports. It must not submit orders.

Run locally:

```bash
docker compose -f docker-compose.demo.pip-first-long-only.yml build
docker compose -f docker-compose.demo.pip-first-long-only.yml up -d usdjpy-pip-first-long-only-dry-run
docker compose -f docker-compose.demo.pip-first-long-only.yml logs -f usdjpy-pip-first-long-only-dry-run
```

Inspect:

```bash
cat reports/ig_demo_audit_pip_first_long_only/bot_run_usdjpy.json
cat reports/ig_demo_audit_pip_first_long_only/signal_dry_run_order_usdjpy.json
tail -50 reports/ig_demo_audit_pip_first_long_only/bot_audit_events_usdjpy.jsonl
```

Stop:

```bash
docker compose -f docker-compose.demo.pip-first-long-only.yml down
```

## DEMO Order-Enabled Docker Path

After you explicitly accept DEMO order placement, use the separate order-enabled compose file:

```text
docker-compose.demo.pip-first-long-only.order.yml
```

It is configured with:

- `IG_ORDER_EXECUTION_ENABLED=true`
- `IG_DRY_RUN_ONLY=false`
- `BOT_CONFIRM=PLACE_DEMO_ORDER`
- fixed deal size `0.5`
- separate audit path `reports/ig_demo_audit_pip_first_long_only_order`

It still points at IG DEMO only. It places an order only when the latest closed 1H candle has a
current long-only signal and all guardrails pass.

Before starting this service, stop the dry-run service so only one pip-first bot is running:

```bash
docker compose -f docker-compose.demo.pip-first-long-only.yml down
```

Start order-enabled DEMO mode:

```bash
docker compose -f docker-compose.demo.pip-first-long-only.order.yml build
docker compose -f docker-compose.demo.pip-first-long-only.order.yml up -d usdjpy-pip-first-long-only-order
docker compose -f docker-compose.demo.pip-first-long-only.order.yml logs -f usdjpy-pip-first-long-only-order
```

Inspect:

```bash
cat reports/ig_demo_audit_pip_first_long_only_order/bot_run_usdjpy.json
cat reports/ig_demo_audit_pip_first_long_only_order/signal_dry_run_order_usdjpy.json
cat reports/ig_demo_audit_pip_first_long_only_order/demo_execution_test.json
tail -100 reports/ig_demo_audit_pip_first_long_only_order/bot_audit_events_usdjpy.jsonl
```

Stop:

```bash
docker compose -f docker-compose.demo.pip-first-long-only.order.yml down
```

## Reproducible Commands

Backtest:

```bash
PYTHONPATH=. .venv/bin/python -m src.main backtest \
  --config config/strategy.usdjpy.fx_swing_trend_reclaim.yaml \
  --normalised-tick-path data/normalised_ticks/USDJPY_2021_2026.parquet \
  --candle-path data/candles/USDJPY_2021_2026 \
  --entry-short-enabled false \
  --entry-long-enabled true \
  --max-trade-duration-days 1 \
  --weekend-policy-name force_close_friday_20_30 \
  --report-output-path reports/pip_first_locked_candidate/long_only
```

Pip-first report:

```bash
LONG_RUN=$(ls -td reports/pip_first_locked_candidate/long_only/* | head -1)

PYTHONPATH=. .venv/bin/python -m src.main pip-first-report \
  --run-path "$LONG_RUN" \
  --starting-balance 28400 \
  --pip-values 0.5,1,2,5 \
  --report-output-path reports/pip_first_locked_candidate/comparison
```

Stress:

```bash
PYTHONPATH=. .venv/bin/python -m src.main pip-first-stress \
  --run-path "$LONG_RUN" \
  --starting-balance 28400 \
  --pip-values 0.5,1,2,5 \
  --iterations 5000 \
  --seed 42 \
  --slippage-pips 0,0.2,0.5,1 \
  --missed-trade-rates 0,0.05,0.1,0.2 \
  --report-output-path reports/pip_first_locked_candidate/stress
```

Decision:

```bash
PYTHONPATH=. .venv/bin/python -m src.main pip-first-decision \
  --comparison-summary reports/pip_first_locked_candidate/comparison/pip_first_summary.csv \
  --stress-summary reports/pip_first_locked_candidate/stress/pip_first_stress_summary.csv \
  --report-output-path reports/pip_first_locked_candidate/decision
```
