#!/usr/bin/env python3
"""Ensure the live USD/JPY news guard calendar has forward coverage.

This wrapper keeps live/demo execution away from the historical 2022-2025
research calendar. If the live CSV is missing or does not cover the requested
forward window, it refreshes the file using the existing Nasdaq calendar fetcher.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.fetch_nasdaq_usdjpy_macro_calendar import (  # noqa: E402
    CalendarEvent,
    fetch_day,
    iter_dates,
    normalise_rows,
    parse_date,
    write_calendar,
)


def _parse_utc(value: str) -> datetime | None:
    text = (value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def latest_calendar_event(path: Path) -> datetime | None:
    if not path.exists() or not path.read_text().strip():
        return None

    latest_event: datetime | None = None
    try:
        with path.open(newline="") as handle:
            for row in csv.DictReader(handle):
                event_time = _parse_utc(row.get("event_time_utc", ""))
                if event_time and (latest_event is None or event_time > latest_event):
                    latest_event = event_time
    except csv.Error:
        return None
    return latest_event


def calendar_status(path: Path, *, now_utc: datetime, min_forward_days: int) -> dict:
    required_until = now_utc + timedelta(days=min_forward_days)
    latest_event = latest_calendar_event(path)
    covers = bool(latest_event and latest_event >= required_until)
    return {
        "covers_min_forward_window": covers,
        "path": str(path),
        "required_until": required_until.isoformat(),
        "latest_event_time_utc": latest_event.isoformat() if latest_event else None,
        "min_forward_days": min_forward_days,
    }


def calendar_covers(path: Path, *, now_utc: datetime, min_forward_days: int) -> bool:
    try:
        return bool(calendar_status(
            path,
            now_utc=now_utc,
            min_forward_days=min_forward_days,
        )["covers_min_forward_window"])
    except csv.Error:
        return False


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
        default="data/macro_calendar/usd_jpy_events_live_nasdaq.csv",
        help="Live news guard CSV path.",
    )
    parser.add_argument(
        "--cache-dir",
        default="data/macro_calendar/cache/nasdaq_live",
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
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    now_utc = datetime.now(timezone.utc)
    output = Path(args.output)

    status = calendar_status(output, now_utc=now_utc, min_forward_days=args.min_forward_days)
    if status["covers_min_forward_window"]:
        print(json.dumps({
            "status": "CURRENT",
            "output": str(output),
            "min_forward_days": args.min_forward_days,
            "latest_event_time_utc": status["latest_event_time_utc"],
            "required_until": status["required_until"],
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
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
