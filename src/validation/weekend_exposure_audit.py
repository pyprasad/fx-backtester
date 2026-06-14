from datetime import datetime, time, timedelta, timezone
import csv
from pathlib import Path


FORCE_CLOSE_REASONS = {"weekend_force_close", "weekend_force_close_exit"}


def normalized_exit_reason(reason: str) -> str:
    value = str(reason or "").strip().lower()
    return "weekend_force_close" if value in FORCE_CLOSE_REASONS else value


def weekend_exposure_audit(trades: list, close_time_utc: str = "20:30") -> list[dict]:
    close_time = time.fromisoformat(close_time_utc)
    return [_audit_trade(trade, close_time) for trade in trades]


def write_weekend_exposure_audit(path: str | Path, rows: list[dict]) -> None:
    path = Path(path)
    with path.open("w", newline="") as handle:
        if not rows:
            handle.write("")
            return
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _audit_trade(trade, close_time: time) -> dict:
    entry, exit_at = trade.entry_timestamp_utc, trade.exit_timestamp_utc
    was_open = any(entry <= cutoff <= exit_at for cutoff in _friday_cutoffs(entry, exit_at, close_time))
    reason = normalized_exit_reason(trade.exit_reason)
    did_force = reason == "weekend_force_close"
    crossed = bool(trade.held_over_weekend) or _crossed_weekend(entry, exit_at)
    return {
        "trade_id": trade.trade_id,
        "entry_timestamp": entry,
        "exit_timestamp": exit_at,
        "exit_reason": reason,
        "was_open_friday_2030_utc": was_open,
        "should_have_force_closed": was_open,
        "did_force_close": did_force,
        "crossed_weekend": crossed,
        "weekend_gap_risk_flag": crossed or (was_open and not did_force),
        "pnl_pips": trade.pnl_pips,
        "pnl_gbp": trade.pnl_gbp,
        "pnl_r": trade.pnl_r,
    }


def _friday_cutoffs(start: datetime, end: datetime, close_time: time):
    day = start.astimezone(timezone.utc).date()
    final = end.astimezone(timezone.utc).date()
    while day <= final:
        if day.weekday() == 4:
            yield datetime.combine(day, close_time, timezone.utc)
        day += timedelta(days=1)


def _crossed_weekend(start: datetime, end: datetime) -> bool:
    day = start.astimezone(timezone.utc).date()
    final = end.astimezone(timezone.utc).date()
    while day <= final:
        if day.weekday() == 5:
            return True
        day += timedelta(days=1)
    return False
