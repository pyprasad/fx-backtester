import json
from dataclasses import asdict
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


def prices_to_candles(response: dict, *, scale_divisor: float | None,
                      symbol: str = "USDJPY", snapshot_timezone: str = "Europe/London") -> pl.DataFrame:
    rows = []
    for item in response.get("prices", []):
        timestamp = _parse_snapshot_time(item, snapshot_timezone)
        prices = {}
        for label, source in (
            ("open", "openPrice"), ("high", "highPrice"),
            ("low", "lowPrice"), ("close", "closePrice"),
        ):
            bid = _scale(item[source]["bid"], scale_divisor)
            ask = _scale(item[source]["ask"], scale_divisor)
            prices[f"bid_{label}"] = bid
            prices[f"ask_{label}"] = ask
            prices[f"mid_{label}"] = _mid(bid, ask)
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
    return pl.DataFrame(rows).sort("timestamp") if rows else pl.DataFrame()


def closed_candles(candles: pl.DataFrame, hours: int, now: datetime | None = None) -> pl.DataFrame:
    now = now or datetime.now(timezone.utc)
    return candles.filter(pl.col("timestamp") + timedelta(hours=hours) <= now)


def runtime_config_from_contract(contract_path: str | Path, runtime_config_path: str | Path):
    config = load_strategy_config(runtime_config_path)
    contract = yaml.safe_load(Path(contract_path).read_text())
    config.indicators.update(contract["indicators"])
    config.entry["short"]["enabled"] = contract["entry_rules"]["signal_filter"]["enabled"]
    config.entry["long"]["enabled"] = False
    config.risk["risk_per_trade_percent"] = contract["risk_management"]["risk_per_trade_percent"]
    config.stop_loss["atr_multiplier"] = contract["stop_loss"]["atr_multiplier"]
    config.exit["partial_take_profit"]["at_r"] = contract["risk_management"]["partial_take_profit_r"]
    config.exit["partial_take_profit"]["close_percent"] = contract["risk_management"]["partial_take_profit_percent"]
    config.exit["move_stop_to_breakeven"]["after_r"] = contract["risk_management"]["move_to_breakeven_after_r"]
    config.exit["runner"]["final_target_r"] = contract["risk_management"]["final_target_r"]
    config.exit["runner"]["trailing_stop"]["atr_multiplier"] = contract["risk_management"]["trailing_atr_multiplier"]
    config.max_trade_duration_days = contract["risk_management"]["maximum_trade_duration_days"]
    config.session_filter = {
        "timezone": "UTC",
        "entry_windows": contract["entry_rules"]["allowed_sessions"],
    }
    config.spread_filter["max_spread_pips"] = contract["spread_guardrails"]["signal_spread_reject_above_pips"]
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
            "target_price": signal.proposed_target,
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
                         market_rules, history_points: int = 300) -> dict:
    hour = closed_candles(prices_to_candles(
        client.get_historical_prices(epic, "HOUR", history_points),
        scale_divisor=ig_config.price_scale_divisor,
    ), 1)
    four_hour = closed_candles(prices_to_candles(
        client.get_historical_prices(epic, "HOUR_4", history_points),
        scale_divisor=ig_config.price_scale_divisor,
    ), 4)
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
