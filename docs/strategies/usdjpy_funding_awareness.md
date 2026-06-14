# USDJPY Funding Awareness

The strategy is swing-mode and may hold overnight. It does not force-close daily unless intraday
mode is explicitly enabled.

## Rules

- Funding timezone: `Europe/London`.
- Funding cutoff: `22:00`.
- Block new entries at/after `21:30`.
- Count each held-through-cutoff event.
- A Wednesday `22:00` crossing counts as three funding days.
- Use configurable pip-cost assumptions only; do not fetch live IG rates in this phase.

## Per-Trade Funding Contract

Record `funding_event_count`, `funding_days`, `wednesday_triple_rollover_count`,
`estimated_funding_pips`, `estimated_funding_r`, `pnl_r_before_funding`, and
`pnl_r_after_funding`.

Raw historical trade P&L must remain unchanged. Funding-adjusted results are separate derived
reports. Before demo execution, IG instrument metadata and current funding methodology must be
validated independently.
