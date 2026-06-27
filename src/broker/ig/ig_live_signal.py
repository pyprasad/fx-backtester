import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import polars as pl
import yaml

from src.broker_guardrails.guardrail_runner import deep_merge
from src.config.config_loader import load_strategy_config
from src.indicators.indicator_engine import add_indicators
from src.strategies.fx_swing_trend_reclaim import generate_signals

from .ig_order_dry_run import build_dry_run_order
from .ig_position_sizing import account_balance, active_account, dynamic_deal_size
from .ig_tick_store import latest_tick


CANDLE_SCHEMA = {
    "timestamp": pl.Datetime(time_zone="UTC"),
    "timestamp_london": pl.Datetime(time_zone="UTC"),
    "symbol": pl.String,
    "bid_open": pl.Float64,
    "ask_open": pl.Float64,
    "mid_open": pl.Float64,
    "bid_high": pl.Float64,
    "ask_high": pl.Float64,
    "mid_high": pl.Float64,
    "bid_low": pl.Float64,
    "ask_low": pl.Float64,
    "mid_low": pl.Float64,
    "bid_close": pl.Float64,
    "ask_close": pl.Float64,
    "mid_close": pl.Float64,
    "spread_open": pl.Float64,
    "spread_high": pl.Float64,
    "spread_low": pl.Float64,
    "spread_close": pl.Float64,
    "spread_avg": pl.Float64,
    "spread_median": pl.Float64,
    "spread_max": pl.Float64,
    "tick_count": pl.Int64,
    "bid_vol_sum": pl.Float64,
    "ask_vol_sum": pl.Float64,
}

PRICE_FIELDS = (
    ("open", "openPrice"),
    ("high", "highPrice"),
    ("low", "lowPrice"),
    ("close", "closePrice"),
)


@dataclass(frozen=True)
class CandleConversion:
    candles: pl.DataFrame
    total_prices: int
    valid_prices: int
    skipped_missing_bid_ask: int

    def quality_summary(self) -> dict:
        return {
            "total_prices": self.total_prices,
            "valid_prices": self.valid_prices,
            "skipped_missing_bid_ask": self.skipped_missing_bid_ask,
        }


def _scale(value, divisor: float | None):
    if value is None:
        return None
    return float(value) / divisor if divisor else float(value)


def _mid(bid, ask):
    return (bid + ask) / 2


def _parse_snapshot_time(item: dict, timezone_name: str) -> datetime:
    if item.get("snapshotTimeUTC"):
        return datetime.fromisoformat(item["snapshotTimeUTC"]).replace(tzinfo=timezone.utc)
    raw = item["snapshotTime"]
    for fmt in ("%Y/%m/%d %H:%M:%S", "%Y:%m:%d-%H:%M:%S"):
        try:
            local = datetime.strptime(raw, fmt).replace(tzinfo=ZoneInfo(timezone_name))
            return local.astimezone(timezone.utc)
        except ValueError:
            pass
    raise ValueError(f"Unsupported IG snapshot time format: {raw}")


def _empty_candle_frame() -> pl.DataFrame:
    return pl.DataFrame(schema=CANDLE_SCHEMA)


def convert_prices_to_candles(response: dict, *, scale_divisor: float | None,
                              symbol: str = "USDJPY",
                              snapshot_timezone: str = "Europe/London") -> CandleConversion:
    rows = []
    total = 0
    skipped_missing_bid_ask = 0
    for item in response.get("prices", []):
        total += 1
        prices = {}
        complete = True
        for label, source in PRICE_FIELDS:
            source_prices = item.get(source) or {}
            bid = _scale(source_prices.get("bid"), scale_divisor)
            ask = _scale(source_prices.get("ask"), scale_divisor)
            if bid is None or ask is None:
                complete = False
                break
            prices[f"bid_{label}"] = bid
            prices[f"ask_{label}"] = ask
            prices[f"mid_{label}"] = _mid(bid, ask)
        if not complete:
            skipped_missing_bid_ask += 1
            continue
        timestamp = _parse_snapshot_time(item, snapshot_timezone)
        close_spread = prices["ask_close"] - prices["bid_close"]
        rows.append({
            "timestamp": timestamp,
            "timestamp_london": timestamp.astimezone(timezone.utc),
            "symbol": symbol,
            **prices,
            "spread_open": prices["ask_open"] - prices["bid_open"],
            "spread_high": prices["ask_high"] - prices["bid_high"],
            "spread_low": prices["ask_low"] - prices["bid_low"],
            "spread_close": close_spread,
            "spread_avg": close_spread,
            "spread_median": close_spread,
            "spread_max": max(
                prices["ask_open"] - prices["bid_open"],
                prices["ask_high"] - prices["bid_high"],
                prices["ask_low"] - prices["bid_low"],
                close_spread,
            ),
            "tick_count": item.get("lastTradedVolume") or 0,
            "bid_vol_sum": 0,
            "ask_vol_sum": 0,
        })
    frame = pl.DataFrame(rows, schema=CANDLE_SCHEMA).sort("timestamp") if rows else _empty_candle_frame()
    return CandleConversion(
        candles=frame,
        total_prices=total,
        valid_prices=len(rows),
        skipped_missing_bid_ask=skipped_missing_bid_ask,
    )


def prices_to_candles(response: dict, *, scale_divisor: float | None,
                      symbol: str = "USDJPY", snapshot_timezone: str = "Europe/London") -> pl.DataFrame:
    return convert_prices_to_candles(
        response,
        scale_divisor=scale_divisor,
        symbol=symbol,
        snapshot_timezone=snapshot_timezone,
    ).candles


def closed_candles(candles: pl.DataFrame, hours: int, now: datetime | None = None) -> pl.DataFrame:
    if "timestamp" not in candles.columns:
        return candles
    now = now or datetime.now(timezone.utc)
    return candles.filter(pl.col("timestamp") + timedelta(hours=hours) <= now)


def derive_four_hour_from_hour(hour: pl.DataFrame, keep_last: int = 1000) -> pl.DataFrame:
    if not hour.height:
        return _empty_candle_frame()
    aggregations = [pl.first("symbol").alias("symbol")]
    for price in ("mid", "bid", "ask"):
        aggregations += [
            pl.first(f"{price}_open").alias(f"{price}_open"),
            pl.max(f"{price}_high").alias(f"{price}_high"),
            pl.min(f"{price}_low").alias(f"{price}_low"),
            pl.last(f"{price}_close").alias(f"{price}_close"),
        ]
    aggregations += [
        pl.first("spread_open").alias("spread_open"),
        pl.max("spread_high").alias("spread_high"),
        pl.min("spread_low").alias("spread_low"),
        pl.last("spread_close").alias("spread_close"),
        pl.mean("spread_avg").alias("spread_avg"),
        pl.median("spread_median").alias("spread_median"),
        pl.max("spread_max").alias("spread_max"),
        pl.sum("tick_count").alias("tick_count"),
        pl.sum("bid_vol_sum").alias("bid_vol_sum"),
        pl.sum("ask_vol_sum").alias("ask_vol_sum"),
    ]
    return (
        hour.sort("timestamp")
        .group_by_dynamic("timestamp", every="4h", label="left", closed="left")
        .agg(aggregations)
        .with_columns(pl.col("timestamp").dt.convert_time_zone("Europe/London").alias("timestamp_london"))
        .sort("timestamp")
        .tail(keep_last)
    )


def runtime_config_from_contract(contract_path: str | Path, runtime_config_path: str | Path):
    config = load_strategy_config(runtime_config_path)
    contract = yaml.safe_load(Path(contract_path).read_text())
    entry_rules = contract["entry_rules"]
    sessions = entry_rules.get("allowed_sessions")
    if sessions is None:
        sessions = [
            {**item, "timezone": contract["time_guards"]["broker_timezone"]}
            for item in entry_rules.get("allowed_london_sessions", [])
        ]
    if not sessions:
        raise ValueError("Strategy contract must define allowed_sessions or allowed_london_sessions")

    config.indicators.update(contract["indicators"])
    config.entry["short"]["enabled"] = entry_rules["signal_filter"]["enabled"]
    config.entry["long"]["enabled"] = False
    config.risk["risk_per_trade_percent"] = contract["risk_management"]["risk_per_trade_percent"]
    config.risk["max_open_trades_total"] = contract["execution"]["max_open_positions"]
    config.risk["max_open_trades_per_market"] = contract["execution"]["max_open_positions"]
    config.stop_loss["atr_multiplier"] = contract["stop_loss"]["atr_multiplier"]
    config.exit["partial_take_profit"]["at_r"] = contract["risk_management"]["partial_take_profit_r"]
    config.exit["partial_take_profit"]["close_percent"] = contract["risk_management"]["partial_take_profit_percent"]
    config.exit["move_stop_to_breakeven"]["after_r"] = contract["risk_management"]["move_to_breakeven_after_r"]
    config.exit["runner"]["final_target_r"] = contract["risk_management"]["final_target_r"]
    config.exit["runner"]["trailing_stop"]["atr_multiplier"] = contract["risk_management"]["trailing_atr_multiplier"]
    config.max_trade_duration_days = contract["risk_management"]["maximum_trade_duration_days"]
    config.execution["default_slippage_points"] = contract["execution"].get(
        "default_slippage_price_points",
        config.execution.get("default_slippage_points", 0),
    )
    config.session_filter = {
        "timezone": "UTC",
        "entry_windows": sessions,
    }
    config.spread_filter["max_spread_pips"] = contract["spread_guardrails"]["signal_spread_reject_above_pips"]
    weekend = contract.get("weekend_policy", {})
    if weekend:
        config.weekend_policy["enabled"] = bool(weekend.get("enabled", False))
        config.weekend_policy["policy_name"] = weekend.get("name", config.weekend_policy.get("policy_name"))
        if "force_close_friday" in weekend:
            config.weekend_policy["force_close_on_friday"] = {
                **config.weekend_policy.get("force_close_on_friday", {}),
                "enabled": bool(weekend["force_close_friday"]),
                "close_time_utc": weekend.get("close_time_utc", "20:30"),
                "close_reason": config.weekend_policy.get("force_close_on_friday", {}).get(
                    "close_reason", "weekend_force_close"
                ),
            }
        config.weekend_policy["block_late_friday_entries"] = {
            **config.weekend_policy.get("block_late_friday_entries", {}),
            "enabled": bool(weekend.get("block_weekend_holding", True)),
            "cutoff_utc": config.weekend_policy.get("block_late_friday_entries", {}).get("cutoff_utc", "17:00"),
        }
    spread_ratio = contract["spread_guardrails"].get("reject_spread_to_risk_ratio_above")
    config.broker_execution_guardrails = deep_merge(config.broker_execution_guardrails, {
        "enabled": True,
        "minimum_initial_risk": {
            "enabled": contract["broker_guardrails"]["reject_initial_risk_below_minimum"],
            "default_min_initial_risk_pips": contract["broker_guardrails"]["min_initial_risk_pips"],
        },
        "spread_to_risk_filter": {
            "enabled": spread_ratio is not None,
            "default_max_spread_to_initial_risk_ratio": spread_ratio or 0.20,
        },
        "abnormal_spread_filter": {
            "enabled": True,
            "max_entry_spread_pips": contract["spread_guardrails"]["signal_spread_reject_above_pips"],
        },
        "entry_time_guard": {
            "enabled": True,
            "timezone": contract["time_guards"]["broker_timezone"],
            "block_new_entries_after": contract["time_guards"]["block_new_entries_after"],
        },
    })
    return config, contract


def _executable_target_from_tick(signal, tick, contract: dict) -> float:
    direction = "SELL" if signal.direction == "SHORT" else "BUY"
    is_short = direction == "SELL"
    entry = tick.bid if is_short else tick.ask
    risk = abs(signal.proposed_stop - entry)
    target_r = float(contract["risk_management"]["final_target_r"])
    return entry - risk * target_r if is_short else entry + risk * target_r


def _signal_payload(signal):
    return {
        **asdict(signal),
        "timestamp_utc": signal.timestamp_utc.isoformat(),
        "timestamp_london": signal.timestamp_london.isoformat(),
    }


def evaluate_live_signal_from_candles(*, client, config, contract: dict, epic: str,
                                      market_rules, hour: pl.DataFrame,
                                      four_hour: pl.DataFrame,
                                      execution_tick=None) -> dict:
    if hour.height < 220 or four_hour.height < 220:
        return {
            "status": "INSUFFICIENT_HISTORY",
            "hour_candles": hour.height,
            "four_hour_candles": four_hour.height,
            "order_sent": False,
        }
    entry = add_indicators(hour, parameters=config.indicators)
    trend = add_indicators(four_hour, parameters=config.indicators)
    signals, rejections = generate_signals(entry, trend, config)
    latest_closed = entry["timestamp"].max()
    current_signals = [signal for signal in signals if signal.timestamp_utc == latest_closed]
    result = {
        "status": "NO_SIGNAL",
        "epic": epic,
        "latest_closed_1h_candle": latest_closed.isoformat() if latest_closed else None,
        "signal_count": len(signals),
        "rejection_count": len(rejections),
        "last_signal": _signal_payload(signals[-1]) if signals else None,
        "current_signal": None,
        "dry_run_order": None,
        "order_sent": False,
    }
    if not current_signals:
        return result

    signal = current_signals[-1]
    result["current_signal"] = _signal_payload(signal)
    tick = execution_tick
    if tick is None or tick.epic != epic:
        result["status"] = "BLOCKED_NO_FRESH_TICK"
        return result
    if abs((datetime.now(timezone.utc) - tick.timestamp_utc).total_seconds()) > 300:
        result["status"] = "BLOCKED_STALE_TICK"
        return result
    accounts = client.get_accounts()
    account = active_account(accounts, client.session.account_id)
    if not account:
        result["status"] = "BLOCKED_NO_ACCOUNT"
        return result
    positions = client.get_open_positions().get("positions", [])
    risk_pips = abs(signal.proposed_stop - tick.bid) / contract["strategy"]["pip_size"]
    size, sizing = dynamic_deal_size(
        balance=account_balance(account),
        risk_percent=float(contract["risk_management"]["risk_per_trade_percent"]),
        stop_distance_pips=risk_pips,
        min_deal_size=market_rules.min_deal_size,
        instrument_unit=market_rules.unit,
    )
    order = build_dry_run_order(
        signal={
            "direction": "SELL" if signal.direction == "SHORT" else "BUY",
            "stop_price": signal.proposed_stop,
            "target_price": _executable_target_from_tick(signal, tick, contract),
        },
        market_rules=market_rules,
        strategy=contract,
        latest_tick=tick,
        size=size,
        open_positions=len(positions),
    )
    result["dry_run_order"] = {
        "payload": order.payload(),
        "validation_status": order.validation_status,
        "validation_errors": order.validation_errors,
        "validation_warnings": order.validation_warnings,
        "sizing": sizing,
        "open_positions": len(positions),
    }
    result["status"] = "SIGNAL_READY_FOR_DEMO_DRY_RUN" if order.validation_status == "READY_FOR_DEMO_DRY_RUN" else "BLOCKED_BY_GUARDRAIL"
    return result


def evaluate_live_signal(*, client, config, contract: dict, ig_config, epic: str,
                         market_rules, history_points: int = 1000) -> dict:
    hour = closed_candles(prices_to_candles(
        client.get_historical_prices(epic, "HOUR", history_points),
        scale_divisor=ig_config.price_scale_divisor,
    ), 1)
    four_hour = derive_four_hour_from_hour(hour, history_points)
    return evaluate_live_signal_from_candles(
        client=client,
        config=config,
        contract=contract,
        epic=epic,
        market_rules=market_rules,
        hour=hour,
        four_hour=four_hour,
        execution_tick=latest_tick(ig_config.tick_output_path),
    )


def write_live_signal_report(output: str | Path, result: dict) -> Path:
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    path = output / "live_signal_check_usdjpy.json"
    path.write_text(json.dumps(result, indent=2, default=str))
    md = output / "live_signal_check_usdjpy.md"
    md.write_text(
        f"# IG DEMO Live Signal Check\n\nStatus: **{result['status']}**\n\n"
        f"Order sent: **{result.get('order_sent', False)}**\n"
    )
    return path


def write_signal_dry_run_report(output: str | Path, result: dict) -> Path:
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": result["status"],
        "epic": result.get("epic"),
        "latest_closed_1h_candle": result.get("latest_closed_1h_candle"),
        "current_signal": result.get("current_signal"),
        "dry_run_order": result.get("dry_run_order"),
        "order_sent": False,
    }
    if result.get("status") == "NO_SIGNAL":
        payload["last_signal"] = result.get("last_signal")
    path = output / "signal_dry_run_order_usdjpy.json"
    path.write_text(json.dumps(payload, indent=2, default=str))
    md = output / "signal_dry_run_order_usdjpy.md"
    md.write_text(
        f"# IG DEMO Signal Dry-Run Order\n\nStatus: **{payload['status']}**\n\n"
        f"Order sent: **False**\n"
    )
    return path
