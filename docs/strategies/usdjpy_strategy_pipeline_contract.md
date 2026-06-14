# USDJPY Strategy Pipeline Contract

## Scope

This contract describes the integration boundary for the final research baseline. It does not
define live order placement. Current runtime dataclasses use some different names; adapters may
map them, but the semantic requirements below must not be lost.

## Required Inputs

| Input | Requirement |
| --- | --- |
| Normalised ticks | Path to sorted USDJPY UTC ticks |
| Signal candles | Closed 1H mid-price candles |
| Trend candles | Closed 4H mid-price candles |
| Strategy contract | `config/strategies/usdjpy_fx_swing_trend_reclaim_v1_final.yaml` |
| Runtime config | Existing executable strategy configuration |
| Broker guardrails | IG distance, selected 3-pip minimum, and time guard |
| Funding assumptions | Configurable daily pip cost and Wednesday rollover rule |
| Account state | Starting/current balance and `0.25%` risk per trade |

Avoid rebuilding candles or renormalising ticks when validated artifacts already exist.

## Data Contracts

### Tick Input

Required: `timestamp_utc` (UTC, unique ordering key), `bid`, `ask`, and `mid`. Optional:
`bid_vol`, `ask_vol`, tick/source identifier. `ask` must be greater than or equal to `bid`.
The normalised project schema uses `timestamp_utc`; external `timestamp` must be mapped explicitly.

### Candle Input

Required semantic fields: timestamp, open, high, low, close, and timeframe. The current project
uses `timestamp`, `mid_open`, `mid_high`, `mid_low`, and `mid_close`. Volume is optional.
Only closed candles may feed signals.

### Signal Output

Each accepted or rejected candidate must expose:

| Field | Type / meaning |
| --- | --- |
| `signal_id` | Stable unique string |
| `timestamp_utc`, `timestamp_london` | Aware datetimes |
| `market`, `direction` | `USDJPY`, `SHORT` |
| `signal_timeframe`, `trend_timeframe` | `1H`, `4H` |
| `entry_reference_price` | Signal-close mid reference |
| `proposed_entry_price` | Actual/estimated executable bid |
| `proposed_stop_price`, `proposed_take_profit_price` | Price levels |
| `initial_risk_pips`, `initial_risk_r` | Distance and normalized risk |
| `entry_spread_pips`, `spread_to_risk_ratio` | Execution-risk context |
| `rsi_value`, `atr_value`, `ema20`, `ema50`, `ema200` | Indicator snapshot |
| `signal_reason`, `rejection_reason` | Machine-readable reason(s) |
| `accepted` | Boolean |

Current `Signal` maps `symbol` to `market`, `signal_price_mid` to `entry_reference_price`,
`proposed_stop`/`proposed_target` to price levels, and `reason_codes` to `signal_reason`. Actual
entry risk and acceptance data are currently distributed across execution and rejection reports;
a future adapter should produce the unified contract.

### Trade Output

Each closed trade must include `trade_id`, `signal_id`, UTC entry/exit timestamps, direction,
entry/exit prices, initial stop, target, initial risk pips, entry/exit spread pips, P&L pips,
`pnl_r_before_funding`, `funding_r`, `pnl_r_after_funding`, exit reason, duration, MFE, and MAE.

Current `Trade` already contains most execution fields. Funding-adjusted fields are produced in
`funding_adjusted_trade_log.csv`; integration should join them by `trade_id`. `pnl_pips` is a
required derived field and is not currently stored directly.

### Guardrail Decision Output

Each guardrail decision must include:

- `signal_id`
- `accepted`
- `rejection_reasons`
- `min_stop_distance_pips`
- `min_initial_risk_pips`
- `actual_initial_risk_pips`
- `entry_spread_pips`
- `spread_to_risk_ratio`
- `timestamp_london`
- `funding_cutoff_proximity`

Current `GuardrailDecision` has most values but not `signal_id`, configured minimum initial risk,
or explicit funding-cutoff proximity. Until a unified adapter is implemented, these values must be
derived from the signal and configured rules and retained in rejection logs.

## Processing Invariants

1. Signals use only closed candles and no future data.
2. Entry uses the first available tick strictly after the signal timestamp.
3. Short fills and barriers use the correct executable side.
4. Broker distance and 3-pip minimum-risk checks run again on executable entry.
5. Only one trade can be open.
6. Funding and weekend events are auditable and timezone-aware.
7. Rejections are explicit; no candidate silently disappears.

## Failure Handling

Missing required data, non-aware timestamps, crossed markets, missing executable ticks, invalid
risk, or unresolved broker metadata must fail closed. Future demo adapters must use idempotency
keys and preserve every requested, rejected, filled, amended, and closed event.
