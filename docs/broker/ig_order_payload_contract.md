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
- Entry is inside the backtested London windows: `07:00-11:30` or `13:00-16:30`.
- No position is open when maximum positions is one.
- Size is positive.
- Spread/risk above `20%` creates a warning.

The CLI uses the latest stored DEMO tick and a hypothetical minimum-risk stop/4R target. DEMO
order size is calculated from active account balance, `risk_per_trade_percent`, current stop
distance in pips, IG `AMOUNT` unit sizing, and the broker minimum deal size. For example, a
`0.25%` risk on a `29,898.03` balance with a `6` pip stop sizes to `12.45`.

The dry-run output always includes `order_sent: false`.

## DEMO Execution-Plumbing Test

This is not a strategy signal and must not be used as strategy-performance evidence. It is
restricted to IG DEMO, refuses stale ticks or existing positions, reruns all dry-run guards, uses
dynamic risk-based sizing, and requires the exact confirmation phrase `PLACE_DEMO_ORDER`.

Temporarily set `IG_ORDER_EXECUTION_ENABLED=true` and `IG_DRY_RUN_ONLY=false`, capture a fresh
price, then run:

```bash
python -m src.main ig-demo-place-test-order \
  --env-file .env.demo \
  --strategy-config config/strategies/usdjpy_fx_swing_trend_reclaim_v1_strict_combined_demo.yaml \
  --epic CS.D.USDJPY.TODAY.IP \
  --confirm PLACE_DEMO_ORDER
```

The execution report records `deal_reference`, `deal_id`, `deal_status`, `accepted`, `reason`,
the IG submission payload, the confirmation response, and the sizing calculation. Immediately
restore `IG_ORDER_EXECUTION_ENABLED=false` and `IG_DRY_RUN_ONLY=true` after the test. Production
execution remains unsupported.
