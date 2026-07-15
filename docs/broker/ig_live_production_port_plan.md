# IG LIVE Production Port Plan

This document defines the required sequence for a future IG LIVE production port. It is a planning
and implementation contract only; the current codebase remains DEMO-only and must not place
real-money orders until this sequence is completed, reviewed, tested, and explicitly approved.

## Current Boundary

The current broker integration is FX-2I:

- `IG_ENV=DEMO`
- `IG_ACC_TYPE=DEMO`
- `IG_REST_BASE_URL=https://demo-api.ig.com/gateway/deal`
- highest readiness status: `READY_FOR_DEMO_DRY_RUN`
- optional DEMO order execution only through explicit `PLACE_DEMO_ORDER`

The existing loader rejects LIVE mode, and the REST client must not be changed casually to bypass
that guard. A LIVE port needs a separate configuration path, command namespace, risk model,
operational controls, tests, and runbook.

## Required Porting Sequence

### 1. Production Readiness Gate

Before implementation, create a signed-off readiness record that confirms:

- the selected research baseline remains `fx_swing_trend_reclaim_v1` with `min_risk_3pips`
- no new optimisation has replaced the selected baseline
- broker-realistic guardrails are still enforced before signal acceptance
- weekend policy remains `force_close_friday_20_30`
- executable-side pricing is preserved
- maximum live risk, daily loss limit, and emergency stop rules are written down

### 2. Configuration Split

Add a new config model instead of weakening `load_ig_demo_config`:

- keep `load_ig_demo_config` DEMO-only
- add a future `load_ig_live_config` with separate validation and defaults
- require `IG_ENV=LIVE`, `IG_ACC_TYPE=LIVE`, and `https://api.ig.com/gateway/deal`
- reject LIVE unless a second explicit confirmation variable is present
- keep token caches, report paths, and tick paths separate from DEMO

The LIVE config must default to read-only mode. Order submission must require a separate explicit
runtime flag and a human-authored deployment confirmation file.

### 3. Live Broker Adapter

Do not reuse DEMO execution names for LIVE. Add a separate adapter with a narrow surface:

- account summary
- market rules
- open positions
- confirms
- historical prices
- read-only streaming
- create position
- close position
- amend stop/limit

Every mutating method must pass through a shared live execution gate. The gate must enforce dry-run
mode, max notional/risk, market status, spread limit, min stop distance, weekend policy, and kill
switch state before any request is sent.

### 4. Order Idempotency And Reconciliation

LIVE order flow needs persistence that survives restarts:

- deterministic deal references
- submitted order journal
- confirm polling journal
- open-position reconciliation on startup
- duplicate-submission prevention
- orphan position detection
- manual intervention status

The bot must reconcile with IG before evaluating any new signal. If state cannot be reconciled,
the process must fail closed and send an operator alert.

### 5. Risk Controls

Minimum LIVE controls:

- per-trade risk cap
- daily realized loss cap
- daily order count cap
- maximum one open USDJPY strategy position unless explicitly approved
- maximum spread cap in pips
- maximum slippage/deviation policy
- margin availability check
- Friday force-close enforcement
- news blackout enforcement
- emergency stop file and Telegram/manual pause support

Risk checks must run before signal acceptance and again immediately before order submission.

### 6. Funding And Broker Cost Awareness

The research funding model is not live IG funding data. LIVE mode needs:

- explicit overnight funding acknowledgement in reports
- funding-aware hold policy documentation
- no mutation of raw strategy P&L reporting
- separate live cost telemetry

Funding awareness must not be used as an optimisation knob.

### 7. Test Layers

Add tests before enabling LIVE order methods:

- config rejects malformed LIVE settings
- LIVE defaults are read-only
- live execution gate blocks without confirmation
- live execution gate blocks on spread, market closed, weekend, and kill switch
- idempotent deal references prevent duplicate creates
- restart reconciliation handles accepted, rejected, pending, and unknown confirms
- lifecycle actions never run without an attached confirmed position
- no secret values appear in logs, reports, reprs, or exceptions

Add integration-test stubs that use fake IG responses. Do not run real LIVE account tests in CI.

### 8. Deployment Runbook

The LIVE runbook must include:

- credential storage and rotation
- one-command preflight
- read-only smoke test
- dry-run signal observation period
- small-size controlled order test
- rollback command
- emergency stop command
- post-incident evidence collection

The runbook must explicitly say that `docker compose config` output must not be pasted into chat or
logs because it expands secrets.

## Non-Goals

- no live trading by changing `.env.prod` alone
- no shared DEMO/LIVE token cache
- no silent conversion of `ig-demo-*` commands into live commands
- no automatic replacement of the selected research baseline
- no production-readiness claim from a single successful order

## Implementation Milestones

1. Add LIVE config and read-only CLI commands.
2. Add live preflight and readiness report with highest status `READY_FOR_LIVE_DRY_RUN`.
3. Add execution gate and fake-client tests.
4. Add persistent order journal and reconciliation.
5. Add live adapter mutating methods behind the execution gate.
6. Add deployment runbook and operator checklist.
7. Run a human-reviewed DEMO bake-off against the final LIVE code path.
8. Require explicit human approval before any real-money order.
