# USDJPY Demo-Readiness Prerequisites

FX-2H selected a research baseline. It did not approve demo or live execution. FX-2I must verify
the following before any demo-order capability is enabled.

## Broker And Market Metadata

- Validate the current IG instrument identifier, trading status, decimal places, pip value, deal
  size increments, minimum size, controlled-risk availability, and live minimum stop/limit distance.
- Validate current spread and reject unacceptable or stale quotes.
- Validate funding methodology and Wednesday rollover against current broker documentation.

## Order And Risk Safety

- Build a dry-run order payload builder with no submission capability by default.
- Implement exact account-currency position sizing and maximum account/strategy risk checks.
- Enforce maximum daily loss, weekly loss, strategy drawdown, and one-position limits.
- Add kill switch, circuit breaker, stale-data detection, duplicate/idempotent order protection,
  and fail-closed behavior.
- Handle order rejection, partial fill, amendment, cancellation, disconnection, and rate limits.

## Operations And Audit

- Maintain immutable logs linking signal, guardrail decision, risk approval, payload, broker
  response, fill, amendment, and close.
- Separate research, demo, and live credentials/environments.
- Add monitoring and reconciliation between intended and broker-reported positions.
- Exercise recovery procedures and human approval workflow.

## Approval Boundary

No real-money execution is allowed without a separate, explicit approval after demo validation.
Passing FX-2I would not by itself authorize live trading.
