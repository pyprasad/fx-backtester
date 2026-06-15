# IG DEMO Dry-Run Order Payload Contract

The dry-run builder creates a hypothetical SELL validation report. It does not send it. The
separate DEMO execution-plumbing command converts a valid dry run to the IG v2 create-position
contract by sending one of each stop/limit distance or level, never both.

## Payload Fields

`deal_reference`, `epic`, `direction`, `size`, `order_type`, optional level, stop distance/level,
limit distance/level, currency, `force_open`, `guaranteed_stop`, `time_in_force`, expiry, and
`dry_run_only=true`. Attached stop/limit orders require `forceOpen=true` in IG's v2 API.

## Mandatory Validation

- Direction is SELL and strategy remains short-only.
- Stop is above bid entry; target is below bid entry.
- Initial executable risk is at least `3` pips and at least broker minimum stop distance.
- Limit distance satisfies broker metadata when available.
- Market status is `TRADEABLE`.
- Latest tick is not delayed.
- Entry is before `21:30 Europe/London`.
- No position is open when maximum positions is one.
- Size is positive.
- Spread/risk above `20%` creates a warning.

The CLI uses the latest stored DEMO tick and a hypothetical minimum-risk stop/4R target. The
execution-plumbing test uses the broker minimum deal size and active account currency.

The dry-run output always includes `order_sent: false`.

## DEMO Execution-Plumbing Test

This is not a strategy signal and must not be used as strategy-performance evidence. It is
restricted to IG DEMO, refuses stale ticks or existing positions, reruns all dry-run guards, uses
the broker minimum size, and requires the exact confirmation phrase `PLACE_DEMO_ORDER`.

Temporarily set `IG_ORDER_EXECUTION_ENABLED=true` and `IG_DRY_RUN_ONLY=false`, capture a fresh
price, then run:

```bash
python -m src.main ig-demo-place-test-order \
  --env-file .env.demo \
  --strategy-config config/strategies/usdjpy_fx_swing_trend_reclaim_v1_final.yaml \
  --epic CS.D.USDJPY.TODAY.IP \
  --confirm PLACE_DEMO_ORDER
```

Immediately restore `IG_ORDER_EXECUTION_ENABLED=false` and `IG_DRY_RUN_ONLY=true` after the test.
Production execution remains unsupported.
