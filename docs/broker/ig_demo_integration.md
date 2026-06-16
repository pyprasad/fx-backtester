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

PYTHONPATH=. .venv/bin/python -m src.main ig-demo-live-signal-check \
  --env-file .env.demo \
  --strategy-config config/strategies/usdjpy_fx_swing_trend_reclaim_v1_strict_combined_demo.yaml \
  --epic <USDJPY_EPIC>

PYTHONPATH=. .venv/bin/python -m src.main ig-demo-signal-dry-run-order \
  --env-file .env.demo \
  --strategy-config config/strategies/usdjpy_fx_swing_trend_reclaim_v1_strict_combined_demo.yaml \
  --epic <USDJPY_EPIC>

PYTHONPATH=. .venv/bin/python -m src.main ig-demo-run-bot \
  --env-file .env.demo \
  --strategy-config config/strategies/usdjpy_fx_swing_trend_reclaim_v1_strict_combined_demo.yaml \
  --epic <USDJPY_EPIC> \
  --history-points 1000 \
  --refresh-points 10 \
  --duration-seconds 3900
```

Reports are written under `reports/ig_demo_audit`; ticks under `data/live_demo_ticks/usdjpy`.
The bot's rolling historical candle cache is written under `data/live_cache/ig`.

## Overnight DEMO Bot Commands

Set shell variables:

```bash
STRICT_CONFIG=config/strategies/usdjpy_fx_swing_trend_reclaim_v1_strict_combined_demo.yaml
EPIC=CS.D.USDJPY.TODAY.IP
```

Pre-flight checks:

```bash
PYTHONPATH=. .venv/bin/python -m src.main ig-demo-open-positions \
  --env-file .env.demo \
  --epic "$EPIC"

PYTHONPATH=. .venv/bin/python -m src.main ig-demo-stream-prices \
  --env-file .env.demo \
  --epic "$EPIC" \
  --duration-seconds 30

PYTHONPATH=. .venv/bin/python -m src.main ig-demo-readiness \
  --env-file .env.demo \
  --strategy-config "$STRICT_CONFIG"

cat reports/ig_demo_audit/ig_demo_readiness_report.json
```

Run without order placement:

```bash
PYTHONPATH=. .venv/bin/python -m src.main ig-demo-run-bot \
  --env-file .env.demo \
  --strategy-config "$STRICT_CONFIG" \
  --epic "$EPIC" \
  --history-points 1000 \
  --refresh-points 5 \
  --duration-seconds 28800 \
  --poll-seconds 5
```

To allow DEMO orders from current strategy signals, set the local `.env.demo` flags:

```dotenv
IG_ORDER_EXECUTION_ENABLED=true
IG_DRY_RUN_ONLY=false
```

Then run with explicit confirmation:

```bash
PYTHONPATH=. .venv/bin/python -m src.main ig-demo-run-bot \
  --env-file .env.demo \
  --strategy-config "$STRICT_CONFIG" \
  --epic "$EPIC" \
  --history-points 1000 \
  --refresh-points 5 \
  --duration-seconds 28800 \
  --poll-seconds 5 \
  --confirm PLACE_DEMO_ORDER
```

Inspect outputs:

```bash
cat data/live_cache/ig/usdjpy_metadata.json
cat reports/ig_demo_audit/bot_run_usdjpy.json
cat reports/ig_demo_audit/signal_dry_run_order_usdjpy.json
cat reports/ig_demo_audit/demo_execution_test.json
tail -20 reports/ig_demo_audit/bot_audit_events_usdjpy.jsonl

PYTHONPATH=. .venv/bin/python -m src.main ig-demo-open-positions \
  --env-file .env.demo \
  --epic "$EPIC"
```

## Safety Boundary

The REST client exposes accounts, sessions, markets, positions, confirms, historical prices, and a
DEMO-gated create-position method. The highest readiness status is `READY_FOR_DEMO_ORDER` when
`.env.demo` explicitly enables DEMO execution; `READY_FOR_LIVE` is prohibited.

DEMO order placement follows IG's REST flow: `POST /positions/otc` returns a `dealReference`, then
`GET /confirms/{dealReference}` returns `dealStatus`, `reason`, and `dealId`. The audit report
`reports/ig_demo_audit/demo_execution_test.json` stores those fields plus the dynamic sizing
calculation. The accepted DEMO order proves broker execution plumbing only; it does not prove
strategy-signal automation because `strategy_signal_used` remains `false`.

The read-only `ig-demo-live-signal-check` command is the first strategy/live bridge. It fetches IG
historical `HOUR` and `HOUR_4` prices, normalizes scaled USDJPY prices with `IG_PRICE_SCALE_DIVISOR`,
applies the strict combined-session strategy contract to the proven runtime strategy engine, and
checks only the latest closed 1H candle. The adjacent `ig-demo-signal-dry-run-order` command writes
`reports/ig_demo_audit/signal_dry_run_order_usdjpy.json` from the same evaluation path. Both commands
write `SIGNAL_READY_FOR_DEMO_DRY_RUN`, `NO_SIGNAL`, or an explicit blocked status, and neither sends
an order.

The `ig-demo-run-bot` command is the long-running process path. It subscribes to IG `PRICE` updates
and keeps only the latest execution tick in memory. It writes audit events for milestones instead of
persisting every tick. IG historical `HOUR` candles remain the signal-generation source of truth. The
bot derives the `HOUR_4` trend frame locally from cached `HOUR` candles using fixed UTC 4-hour
anchors (`00:00`, `04:00`, `08:00`, `12:00`, `16:00`, `20:00`) so live signal generation matches the
backtest candle grid. Lightstreamer ticks are used for executable-entry validation only.
`--history-points` controls first-time cache bootstrap size; once cache files exist, `--refresh-points`
controls the much smaller hourly historical refresh. If IG historical allowance is exceeded and cache
files already exist, the bot falls back to the existing cache and writes that decision into audit.

For temporary DEMO validation only, `.env.demo` may include `IG_HISTORICAL_API_KEY`,
`IG_HISTORICAL_USERNAME`, and `IG_HISTORICAL_PASSWORD`. When all three are set, the bot uses that
second DEMO session only for historical candle reads. Streaming, account balance, open positions,
dry-run validation, order submission, and confirms remain on the primary `IG_*` account. Use a
separate `IG_HISTORICAL_TOKEN_CACHE_PATH` to avoid session-token mixing.

The initial session uses IG session version 2 because it returns CST and X-SECURITY-TOKEN needed
for Lightstreamer. If `IG_ACCOUNT_ID` differs from the authenticated current account, readiness
fails; automatic account switching is not implemented in FX-2I.

Primary references:

- IG REST guide: https://labs.ig.com/rest-trading-api-guide.html
- Lightstreamer Python SDK: https://lightstreamer.com/sdks/ls-python-client/2.1.0/api/lightstreamer.html
