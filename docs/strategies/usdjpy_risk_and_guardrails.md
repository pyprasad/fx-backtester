# USDJPY Risk And Guardrails

## Position Risk

- Risk `0.25%` of current research balance per trade.
- Maximum one open trade and one USDJPY trade.
- No pyramiding, averaging down, martingale, or manual backtest override.
- Current position sizing is simplified and requires exact account-currency pip-value validation
  before demo execution.

## Mandatory Guardrails

The selected candidate is `min_risk_3pips`.

| Guardrail | Rule |
| --- | --- |
| Broker minimum stop | Reject below `2.0` pips |
| Broker minimum take profit | Reject below `2.0` pips |
| Selected minimum initial risk | Reject below `3.0` pips |
| Entry time | Block at/after `21:30 Europe/London` |
| Weekend | Force close Friday `20:30 UTC`; no weekend holding |

Distance and minimum-risk checks must run against the actual next executable entry tick, not only
the signal candle close.

## Spread Awareness

Track entry spread, exit spread, initial risk, and spread-to-initial-risk ratio. Warn above `20%`.
The selected baseline does not impose a separate spread/risk rejection threshold, but the existing
absolute signal spread limit remains `2.0` pips. Any future rejection threshold requires a new
controlled validation rather than a silent config change.

## Candidate Boundary

`ig_min_stop_only` is the documented backup. `recommended_research_guardrail` must not be silently
substituted because it was rejected as unnecessarily conservative in FX-2H.
