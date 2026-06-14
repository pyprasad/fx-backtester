# IG DEMO Streaming Notes

## Supported Subscriptions

- Price: `PRICE:{accountId}:{epic}` using `MERGE`
- Optional chart ticks: `CHART:{epic}:TICK` using `DISTINCT`
- Optional read-only trade updates: `TRADE:{accountId}` using `CONFIRMS`, `OPU`, and `WOU`

Deprecated `MARKET:{epic}` subscriptions are rejected by configuration and client construction.
Observed legacy companion `BID`/`OFFER` field names can be normalized for diagnostics, but the
integration continues to subscribe through modern `PRICE:{accountId}:{epic}`.

PRICE fields are `BIDPRICE1`, `ASKPRICE1`, `TIMESTAMP`, `DELAY`, `DLG_FLAG`, `HIGH`, `LOW`, and
`MID_OPEN`. CHART fields are `BID`, `OFR`, `LTP`, and `UTM`.

## Normalized Tick

Each update becomes an aware UTC `InternalTick` with bid, ask, mid, spread pips, source, EPIC,
delayed flag, optional volumes, and retained raw update. CSV output contains `timestamp`,
`bid`, `ask`, `mid`, optional volumes, `spread_pips`, `source`, `epic`, and `delayed`.

Some broker displays expose scaled integer-like prices. Set `IG_PRICE_SCALE_DIVISOR` only after
confirming the scale from observed quotes and market metadata. Without it, an implausibly large FX
price is rejected. The applied divisor is retained in the tick raw data and checked by readiness.
For example, divisor `100` converts `16018 / 16025` to `160.18 / 160.25`; with USDJPY pip size
`0.01`, the spread is `7` pips.

`DELAY=1` marks PRICE data delayed and prevents readiness or dry-run order validation. The
Lightstreamer SDK handles reconnect/re-subscribe behavior; listeners remain lightweight and append
ticks immediately. Streaming shutdown always disconnects and logs out.

PRICE `TIMESTAMP` may contain time-of-day without a date. FX-2I combines it with the current UTC
date; this assumption must be verified against observed DEMO updates before later order testing.
