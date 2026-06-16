# FX-2I IG DEMO Integration

FX-2I provides IG DEMO REST access, read-only Lightstreamer prices, local tick capture,
market-rule validation, dry-run order validation, and an explicitly gated DEMO
execution-plumbing test with dynamic risk-based sizing. Live-account orders are prohibited.

## Setup

1. Install dependencies with `python3.11 -m pip install -e ".[dev]"`.
2. Copy `.env.demo.example` to `.env.demo`.
3. Add DEMO credentials only to `.env.demo`; it is gitignored.
4. Leave `IG_ORDER_EXECUTION_ENABLED=false` and `IG_DRY_RUN_ONLY=true`.
5. Leave `IG_TOKEN_CACHE_ENABLED=true` to reuse the REST session tokens required by Lightstreamer.

Never provide credentials in chat or commit them. The loader rejects LIVE mode and inconsistent
execution flags.

The session cache is written to the gitignored `.runtime/ig_demo_session.json` with owner-only
permissions. Cached `CST` and `X-SECURITY-TOKEN` values are reused across CLI commands; if IG
rejects an expired cached session, the REST client creates and saves a replacement session.

The optional `ig-demo-place-test-order` command is a DEMO execution-plumbing test. It uses a
synthetic SELL order rather than a strategy-generated signal, sizes from active DEMO account
balance and `risk_per_trade_percent`, requires explicit confirmation, and cannot target a live
account. See `docs/broker/ig_order_payload_contract.md`.

## Recommended Command Sequence

```bash
PYTHONPATH=. .venv/bin/python -m src.main ig-demo-auth-check --env-file .env.demo

PYTHONPATH=. .venv/bin/python -m src.main ig-demo-market-discovery \
  --env-file .env.demo --market "USD/JPY"

PYTHONPATH=. .venv/bin/python -m src.main ig-demo-market-rules \
  --env-file .env.demo --epic <USDJPY_EPIC>

PYTHONPATH=. .venv/bin/python -m src.main ig-demo-stream-prices \
  --env-file .env.demo --epic <USDJPY_EPIC> --duration-seconds 120

PYTHONPATH=. .venv/bin/python -m src.main ig-demo-dry-run-order \
  --env-file .env.demo \
  --strategy-config config/strategies/usdjpy_fx_swing_trend_reclaim_v1_strict_combined_demo.yaml \
  --epic <USDJPY_EPIC>

PYTHONPATH=. .venv/bin/python -m src.main ig-demo-readiness \
  --env-file .env.demo \
  --strategy-config config/strategies/usdjpy_fx_swing_trend_reclaim_v1_strict_combined_demo.yaml
```

Reports are written under `reports/ig_demo_audit`; ticks under `data/live_demo_ticks/usdjpy`.

## Safety Boundary

The REST client exposes accounts, sessions, markets, positions, confirms, historical prices, and a
DEMO-gated create-position method. The highest readiness status is `READY_FOR_DEMO_ORDER` when
`.env.demo` explicitly enables DEMO execution; `READY_FOR_LIVE` is prohibited.

DEMO order placement follows IG's REST flow: `POST /positions/otc` returns a `dealReference`, then
`GET /confirms/{dealReference}` returns `dealStatus`, `reason`, and `dealId`. The audit report
`reports/ig_demo_audit/demo_execution_test.json` stores those fields plus the dynamic sizing
calculation. The accepted DEMO order proves broker execution plumbing only; it does not prove
strategy-signal automation because `strategy_signal_used` remains `false`.

The initial session uses IG session version 2 because it returns CST and X-SECURITY-TOKEN needed
for Lightstreamer. If `IG_ACCOUNT_ID` differs from the authenticated current account, readiness
fails; automatic account switching is not implemented in FX-2I.

Primary references:

- IG REST guide: https://labs.ig.com/rest-trading-api-guide.html
- Lightstreamer Python SDK: https://lightstreamer.com/sdks/ls-python-client/2.1.0/api/lightstreamer.html
