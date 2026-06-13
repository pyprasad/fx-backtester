from datetime import datetime, time, timedelta
from uuid import uuid4


def _at_or_after(timestamp: datetime, value: str) -> bool:
    return timestamp.weekday() == 4 and timestamp.time() >= time.fromisoformat(value)


class WeekendPolicy:
    """UTC-only weekend entry and open-position policy decisions."""

    def __init__(self, config: dict | None):
        self.config = config or {"enabled": False}
        self.enabled = self.config.get("enabled", False)
        self.policy_name = self.config.get("policy_name", "baseline_allow_weekend")

    def is_after_friday_cutoff(self, timestamp_utc: datetime, cutoff_utc: str) -> bool:
        return _at_or_after(timestamp_utc, cutoff_utc)

    def is_friday_force_close_time(self, timestamp_utc: datetime, close_time_utc: str) -> bool:
        return _at_or_after(timestamp_utc, close_time_utc)

    def is_sunday_open_blocked(
        self, timestamp_utc: datetime, week_open_timestamp_utc: datetime, minutes_after_week_open: int
    ) -> bool:
        return week_open_timestamp_utc <= timestamp_utc < week_open_timestamp_utc + timedelta(minutes=minutes_after_week_open)

    def should_block_new_entry(self, timestamp_utc: datetime) -> tuple[bool, str]:
        if not self.enabled:
            return False, ""
        section = self.config.get("block_new_trades_after_friday", {})
        if section.get("enabled") and self.is_after_friday_cutoff(timestamp_utc, section["cutoff_utc"]):
            return True, "REJECT_WEEKEND_POLICY_FRIDAY_CUTOFF"
        section = self.config.get("block_late_friday_entries", {})
        if section.get("enabled") and self.is_after_friday_cutoff(timestamp_utc, section["cutoff_utc"]):
            return True, "REJECT_WEEKEND_POLICY_LATE_FRIDAY"
        return False, ""

    def should_block_sunday_open_entry(self, timestamp_utc: datetime, week_open_timestamp_utc: datetime) -> tuple[bool, str]:
        section = self.config.get("block_sunday_open_entries", {})
        blocked = self.enabled and section.get("enabled") and self.is_sunday_open_blocked(
            timestamp_utc, week_open_timestamp_utc, section["minutes_after_week_open"]
        )
        return (True, "REJECT_WEEKEND_POLICY_SUNDAY_OPEN") if blocked else (False, "")

    def _decision(self, key: str, timestamp: datetime, open_r: float | None = None) -> tuple[bool, str]:
        section = self.config.get(key, {})
        field = "apply_time_utc" if key == "tighten_stop_before_weekend" else "close_time_utc"
        if not self.enabled or not section.get("enabled") or not self.is_friday_force_close_time(timestamp, section[field]):
            return False, ""
        if key == "close_only_if_losing_on_friday" and open_r is not None and open_r >= 0:
            return False, ""
        if key == "close_only_if_not_in_profit_threshold" and open_r is not None and open_r >= section["min_open_trade_r_to_keep"]:
            return False, ""
        if key in {"reduce_position_before_weekend", "tighten_stop_before_weekend"} and open_r is not None and open_r < section["min_open_trade_r_to_apply"]:
            return False, ""
        return True, section.get("close_reason") or section.get("reason", "")

    def should_force_close_trade(self, trade, current_tick_timestamp_utc) -> tuple[bool, str]:
        return self._decision("force_close_on_friday", current_tick_timestamp_utc)

    def should_close_losing_trade(self, trade, current_tick_timestamp_utc, open_r) -> tuple[bool, str]:
        return self._decision("close_only_if_losing_on_friday", current_tick_timestamp_utc, open_r)

    def should_close_below_profit_threshold(self, trade, current_tick_timestamp_utc, open_r) -> tuple[bool, str]:
        return self._decision("close_only_if_not_in_profit_threshold", current_tick_timestamp_utc, open_r)

    def should_reduce_position(self, trade, current_tick_timestamp_utc, open_r) -> tuple[bool, float, str]:
        yes, reason = self._decision("reduce_position_before_weekend", current_tick_timestamp_utc, open_r)
        return yes, self.config.get("reduce_position_before_weekend", {}).get("close_percent", 0), reason

    def should_tighten_stop(self, trade, current_tick_timestamp_utc, open_r) -> tuple[bool, str]:
        return self._decision("tighten_stop_before_weekend", current_tick_timestamp_utc, open_r)

    def is_held_over_weekend(self, entry: datetime, exit_: datetime) -> bool:
        friday = entry + timedelta(days=(4 - entry.weekday()) % 7)
        return entry <= friday.replace(hour=23, minute=59) and exit_ >= friday + timedelta(days=2)

    def event(self, event_type: str, timestamp: datetime, **values) -> dict:
        return {
            "event_id": str(uuid4()), "policy_name": self.policy_name, "timestamp_utc": timestamp,
            "symbol": values.get("symbol", "USDJPY"), "event_type": event_type,
            "trade_id": values.get("trade_id"), "signal_id": values.get("signal_id"),
            "direction": values.get("direction"), "price": values.get("price"),
            "open_r_before_event": values.get("open_r"), "position_percent_affected": values.get("percent"),
            "old_stop": values.get("old_stop"), "new_stop": values.get("new_stop"),
            "reason": values.get("reason", ""), "notes": values.get("notes", ""),
        }
