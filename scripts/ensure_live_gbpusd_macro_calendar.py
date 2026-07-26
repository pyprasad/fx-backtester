#!/usr/bin/env python3
"""Ensure the live GBP/USD news guard calendar has forward coverage."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ensure_live_usdjpy_macro_calendar import (  # noqa: E402
    calendar_covers,
    calendar_status,
    latest_calendar_event,
    prune_calendar,
)
from scripts.fetch_nasdaq_gbpusd_macro_calendar import (  # noqa: E402
    CalendarEvent,
    fetch_day,
    iter_dates,
    normalise_rows,
    parse_date,
    write_calendar,
)


def refresh_calendar(
    *,
    start_date: str,
    end_date: str,
    output: Path,
    cache_dir: Path,
    refresh_cache: bool,
    sleep_seconds: float,
    timeout_seconds: int,
    retries: int,
    retry_sleep_seconds: float,
) -> dict:
    start = parse_date(start_date)
    end = parse_date(end_date)
    if end < start:
        raise SystemExit("--end-date must be on or after --start-date")

    all_events: list[CalendarEvent] = []
    fetched_days = 0
    cache_hits = 0
    for day in iter_dates(start, end):
        cache_file = cache_dir / f"{day.isoformat()}.json"
        used_cache = cache_file.exists() and not refresh_cache
        rows = fetch_day(
            day,
            cache_dir,
            refresh_cache,
            timeout_seconds,
            retries,
            retry_sleep_seconds,
        )
        all_events.extend(normalise_rows(day, rows))
        fetched_days += 1
        cache_hits += int(used_cache)
        if not used_cache and sleep_seconds > 0:
            import time

            time.sleep(sleep_seconds)

    write_calendar(output, all_events)
    return {
        "status": "REFRESHED",
        "output": str(output),
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "calendar_days": fetched_days,
        "cache_hits": cache_hits,
        "events_written": len(all_events),
        "source": "nasdaq_economic_calendar",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        default="data/macro_calendar/gbp_usd_events_live_nasdaq.csv",
        help="Live news guard CSV path.",
    )
    parser.add_argument(
        "--cache-dir",
        default="data/macro_calendar/cache/nasdaq_live_gbpusd",
        help="Per-day Nasdaq JSON cache directory.",
    )
    parser.add_argument("--forward-days", type=int, default=21)
    parser.add_argument("--min-forward-days", type=int, default=7)
    parser.add_argument("--start-date", help="Override start date, YYYY-MM-DD.")
    parser.add_argument("--end-date", help="Override end date, YYYY-MM-DD.")
    parser.add_argument("--sleep-seconds", type=float, default=0.25)
    parser.add_argument("--timeout-seconds", type=int, default=30)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--retry-sleep-seconds", type=float, default=5.0)
    parser.add_argument("--refresh-cache", action="store_true")
    parser.add_argument("--prune-past-events", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument(
        "--prune-retention-hours",
        type=int,
        default=24,
        help="Keep recent past events for post-news blackout/audit safety; timestamps are UTC.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    now_utc = datetime.now(timezone.utc)
    output = Path(args.output)

    prune = (
        prune_calendar(output, now_utc=now_utc, retention_hours=args.prune_retention_hours)
        if args.prune_past_events else {"enabled": False}
    )
    status = calendar_status(output, now_utc=now_utc, min_forward_days=args.min_forward_days)
    if status["covers_min_forward_window"]:
        print(json.dumps({
            "status": "CURRENT",
            "output": str(output),
            "min_forward_days": args.min_forward_days,
            "latest_event_time_utc": status["latest_event_time_utc"],
            "required_until": status["required_until"],
            "prune": prune,
        }, indent=2))
        return

    start_date = args.start_date or now_utc.date().isoformat()
    end_date = args.end_date or (now_utc.date() + timedelta(days=args.forward_days)).isoformat()
    result = refresh_calendar(
        start_date=start_date,
        end_date=end_date,
        output=output,
        cache_dir=Path(args.cache_dir),
        refresh_cache=args.refresh_cache,
        sleep_seconds=args.sleep_seconds,
        timeout_seconds=args.timeout_seconds,
        retries=args.retries,
        retry_sleep_seconds=args.retry_sleep_seconds,
    )
    if args.prune_past_events:
        result["prune"] = prune_calendar(
            output,
            now_utc=now_utc,
            retention_hours=args.prune_retention_hours,
        )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
