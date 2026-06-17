from datetime import time
from uuid import uuid4
from zoneinfo import ZoneInfo

import polars as pl

from src.config.schemas import StrategyConfig
from src.broker_guardrails.distance_validator import evaluate_proposed_signal
from src.news_guard.blackout import is_news_blackout
from src.news_guard.calendar_loader import load_economic_events
from src.risk.weekend_policy import WeekendPolicy

from .signal import Signal


def _session(timestamp_utc, windows: list[dict], default_timezone: str) -> tuple[str | None, object]:
    for window in windows:
        local = timestamp_utc.astimezone(ZoneInfo(window.get("timezone", default_timezone)))
        current = local.time()
        start, end = time.fromisoformat(window["start"]), time.fromisoformat(window["end"])
        if start <= current <= end:
            return window["name"], local
    return None, timestamp_utc.astimezone(ZoneInfo(default_timezone))


def generate_signals(entry: pl.DataFrame, trend: pl.DataFrame, config: StrategyConfig) -> tuple[list[Signal], list[dict]]:
    aliases = {
        "ema_fast": f"ema_{config.indicators['ema_fast']}",
        "ema_mid": f"ema_{config.indicators['ema_mid']}",
        "ema_slow": f"ema_{config.indicators['ema_slow']}",
        "rsi": f"rsi_{config.indicators['rsi_period']}",
        "atr": f"atr_{config.indicators['atr_period']}",
        "atr_pips": f"atr_{config.indicators['atr_period']}_pips",
    }
    entry = entry.with_columns(
        *(pl.col(source).alias(target) for target, source in aliases.items()
          if target not in entry.columns and source in entry.columns)
    )
    trend = trend.with_columns(
        *(pl.col(source).alias(target) for target, source in aliases.items()
          if target not in trend.columns and source in trend.columns)
    )
    trend_view = trend.select("timestamp", pl.col("mid_close").alias("trend_close"), "ema_slow")
    joined = entry.sort("timestamp").join_asof(trend_view.sort("timestamp"), on="timestamp", strategy="backward")
    signals, rejected = [], []
    weekend = WeekendPolicy(config.weekend_policy)
    guardrails = config.broker_execution_guardrails
    news_guard = config.news_guard or {}
    news_events = []
    if news_guard.get("enabled"):
        calendar_file = config.base_dir / news_guard["calendar_file"]
        news_events = load_economic_events(
            calendar_file,
            news_guard.get("affected_currencies", []),
            news_guard.get("impact_levels", []),
        )

    def news_rejection(row: dict, direction: str) -> bool:
        if not news_guard.get("enabled") or not news_guard.get("block_new_entries", True):
            return False
        blocked, event = is_news_blackout(
            row["timestamp"],
            news_events,
            int(news_guard.get("before_minutes", 0)),
            int(news_guard.get("after_minutes", 0)),
        )
        if not blocked or event is None:
            return False
        if news_guard.get("log_skipped_signals", True):
            rejected.append({
                "timestamp": row["timestamp"],
                "timestamp_utc": row["timestamp"],
                "strategy": config.strategy["name"],
                "market": config.strategy["market"],
                "signal_direction": direction,
                "reason": "NEWS_BLACKOUT",
                "rejection_reason": "NEWS_BLACKOUT",
                "rejection_group": "NEWS_GUARD",
                "event_id": event.event_id,
                "event_name": event.event_name,
                "event_currency": event.currency,
                "event_time_utc": event.event_time_utc,
                "impact": event.impact,
            })
        return True

    def guardrail_rejection(row, stop, target, spread_pips, session):
        if not guardrails.get("enabled"):
            return False
        decision = evaluate_proposed_signal(
            row["timestamp"], row["mid_close"], stop, target, spread_pips, guardrails
        )
        if decision.accepted:
            return False
        groups = {
            "REJECT_BELOW_BROKER_MIN_STOP_DISTANCE": "BROKER_DISTANCE",
            "REJECT_BELOW_BROKER_MIN_TP_DISTANCE": "BROKER_DISTANCE",
            "REJECT_BELOW_MIN_INITIAL_RISK_PIPS": "MIN_RISK",
            "REJECT_ENTRY_SPREAD_ABOVE_MAX": "SPREAD_RISK",
            "REJECT_SPREAD_TO_RISK_RATIO_TOO_HIGH": "SPREAD_RISK",
            "REJECT_AFTER_FUNDING_ENTRY_CUTOFF": "FUNDING_TIME_GUARD",
        }
        for reason in decision.rejection_reasons:
            rejected.append({
                "timestamp": row["timestamp"], "timestamp_utc": row["timestamp"],
                "rejection_reason": reason, "reason": reason, "rejection_group": groups[reason],
                "initial_risk_pips": decision.initial_risk_pips,
                "entry_spread_pips": decision.entry_spread_pips,
                "spread_to_risk_ratio": decision.spread_to_risk_ratio,
                "min_required_stop_distance_pips": decision.min_stop_distance_pips,
                "configured_min_initial_risk_pips": guardrails["minimum_initial_risk"]["default_min_initial_risk_pips"],
                "timestamp_london": decision.timestamp_local, "hour_london": decision.timestamp_local.hour,
                "day_of_week_london": decision.timestamp_local.strftime("%A"), "session_label": session,
                "warnings": "|".join(decision.warnings),
            })
        return True

    def weekend_rejection(row: dict, session: str | None) -> str | None:
        blocked, reason = weekend.should_block_new_entry(row["timestamp"])
        if not blocked and row["timestamp"].weekday() == 6:
            week_open = row["timestamp"].replace(hour=21, minute=0, second=0, microsecond=0)
            blocked, reason = weekend.should_block_sunday_open_entry(row["timestamp"], week_open)
        if not blocked:
            return None
        rejected.append({
            "timestamp": row["timestamp"], "timestamp_utc": row["timestamp"],
            "reason": reason, "rejection_reason": reason,
            "day_of_week": row["timestamp"].strftime("%A"), "hour_utc": row["timestamp"].hour,
            "policy_name": weekend.policy_name, "session_label": session,
        })
        return reason

    rows = joined.with_columns(pl.col("rsi").shift(1).alias("previous_rsi")).to_dicts()
    for row in rows:
        if any(row.get(k) is None for k in ("atr", "ema_fast", "ema_mid", "rsi", "ema_slow")):
            continue
        session, session_local = _session(
            row["timestamp"], config.session_filter["entry_windows"],
            config.session_filter["timezone"],
        )
        spread_pips = row["spread_avg"] / 0.01
        common_reason = None
        if not session:
            common_reason = "outside_session"
        elif config.market_open_filter.get("avoid_sunday_open") and session_local.weekday() == 6:
            common_reason = "sunday_open"
        elif spread_pips > config.spread_filter["max_spread_pips"]:
            common_reason = "spread_too_high"
        if common_reason:
            rejected.append({
                "timestamp": row["timestamp"], "timestamp_utc": row["timestamp"],
                "reason": common_reason, "rejection_reason": common_reason,
                "day_of_week": row["timestamp"].strftime("%A"), "hour_utc": row["timestamp"].hour,
                "policy_name": weekend.policy_name, "session_label": session,
            })
            continue
        bearish = row["mid_close"] < row["mid_open"]
        near_ema = min(abs(row["mid_close"] - row["ema_fast"]), abs(row["mid_close"] - row["ema_mid"])) <= (
            config.entry["short"]["max_pullback_atr"] * row["atr"]
        )
        rsi_trigger = config.entry["short"]["rsi_cross_down_level"]
        rsi_down = row["rsi"] < rsi_trigger and row["previous_rsi"] is not None and row["rsi"] < row["previous_rsi"]
        if config.entry["short"]["enabled"] and row["trend_close"] < row["ema_slow"] and row["mid_close"] < row["ema_mid"] and near_ema and rsi_down and bearish:
            if weekend_rejection(row, session):
                continue
            stop = max(row["mid_high"], row["mid_close"] + config.stop_loss["atr_multiplier"] * row["atr"])
            risk = stop - row["mid_close"]
            target = row["mid_close"] - config.exit["runner"]["final_target_r"] * risk
            if guardrail_rejection(row, stop, target, spread_pips, session):
                continue
            if news_rejection(row, "SHORT"):
                continue
            signals.append(Signal(
                str(uuid4()), row["timestamp"], session_local, row["symbol"], "SHORT",
                "market_on_next_tick_after_signal_close", row["mid_close"], "4H", "1H",
                ["trend_below_ema200", "pullback", "rsi_rejection", "bearish_close"],
                {k: row[k] for k in ("ema_fast", "ema_mid", "ema_slow", "rsi", "atr", "atr_pips")},
                stop, target, spread_pips, session,
            ))
        if config.entry["long"]["enabled"]:
            bullish = row["mid_close"] > row["mid_open"]
            rsi_up = row["rsi"] > config.entry["long"]["rsi_cross_up_level"] and row["previous_rsi"] is not None and row["rsi"] > row["previous_rsi"]
            if row["trend_close"] > row["ema_slow"] and row["mid_close"] > row["ema_mid"] and near_ema and rsi_up and bullish:
                if weekend_rejection(row, session):
                    continue
                stop = min(row["mid_low"], row["mid_close"] - config.stop_loss["atr_multiplier"] * row["atr"])
                risk = row["mid_close"] - stop
                target = row["mid_close"] + config.exit["runner"]["final_target_r"] * risk
                if guardrail_rejection(row, stop, target, spread_pips, session):
                    continue
                if news_rejection(row, "LONG"):
                    continue
                signals.append(Signal(
                    str(uuid4()), row["timestamp"], session_local, row["symbol"], "LONG",
                    "market_on_next_tick_after_signal_close", row["mid_close"], "4H", "1H",
                    ["trend_above_ema200", "pullback", "rsi_reclaim", "bullish_close"],
                    {k: row[k] for k in ("ema_fast", "ema_mid", "ema_slow", "rsi", "atr", "atr_pips")},
                    stop, target, spread_pips, session,
                ))
    return signals, rejected
