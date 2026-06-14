# IG DEMO Dry-Run Order Payload Contract

The dry-run builder creates a hypothetical IG-compatible SELL payload and validation report. It
does not send it.

## Payload Fields

`deal_reference`, `epic`, `direction`, `size`, `order_type`, optional level, stop distance/level,
limit distance/level, currency, `force_open`, `guaranteed_stop`, `time_in_force`, expiry, and
`dry_run_only=true`.

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

The CLI uses the latest stored DEMO tick and a hypothetical minimum-risk stop/4R target. Exact
account-currency sizing and broker payload acceptance remain FX-2I/next-phase gaps.

The output report always includes `order_sent: false`. No REST order endpoint is implemented.
