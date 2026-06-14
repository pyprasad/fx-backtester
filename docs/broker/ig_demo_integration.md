# FX-2I IG DEMO Integration

FX-2I provides read-only IG DEMO REST access, read-only Lightstreamer prices, local tick capture,
market-rule validation, and dry-run order payload validation. It cannot submit an order.

## Setup

1. Install dependencies with `python3.11 -m pip install -e ".[dev]"`.
2. Copy `.env.demo.example` to `.env.demo`.
3. Add DEMO credentials only to `.env.demo`; it is gitignored.
4. Leave `IG_ORDER_EXECUTION_ENABLED=false` and `IG_DRY_RUN_ONLY=true`.

Never provide credentials in chat or commit them. The loader rejects LIVE mode and enabled order
execution.

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
  --strategy-config config/strategies/usdjpy_fx_swing_trend_reclaim_v1_final.yaml \
  --epic <USDJPY_EPIC>

PYTHONPATH=. .venv/bin/python -m src.main ig-demo-readiness \
  --env-file .env.demo \
  --strategy-config config/strategies/usdjpy_fx_swing_trend_reclaim_v1_final.yaml
```

Reports are written under `reports/ig_demo_audit`; ticks under `data/live_demo_ticks/usdjpy`.

## Safety Boundary

The REST client exposes accounts, sessions, markets, positions, confirms, and historical prices.
It deliberately has no create-position/order method. The highest possible readiness status is
`READY_FOR_DEMO_DRY_RUN`; `READY_FOR_LIVE` is prohibited.

The initial session uses IG session version 2 because it returns CST and X-SECURITY-TOKEN needed
for Lightstreamer. If `IG_ACCOUNT_ID` differs from the authenticated current account, readiness
fails; automatic account switching is not implemented in FX-2I.

Primary references:

- IG REST guide: https://labs.ig.com/rest-trading-api-guide.html
- Lightstreamer Python SDK: https://lightstreamer.com/sdks/ls-python-client/2.1.0/api/lightstreamer.html
