#!/usr/bin/env python3
"""Fetch a cached USD/JPY macro calendar from Nasdaq's public economic calendar.

The output is the CSV shape consumed by src.news_guard.calendar_loader.
Each calendar day is cached separately so reruns do not repeat network requests.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, time as datetime_time, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


NASDAQ_URL = "https://api.nasdaq.com/api/calendar/economicevents"

CSV_FIELDS = [
    "event_id",
    "event_time_utc",
    "country",
    "currency",
    "event_name",
    "impact",
    "actual",
    "forecast",
    "previous",
    "source",
]

COUNTRY_TO_CURRENCY = {
    "United States": "USD",
    "Japan": "JPY",
}

HIGH_IMPACT_PATTERNS = {
    "USD": [
        r"\bADP\b",
        r"\bCPI\b",
        r"\bFOMC\b",
        r"\bGDP\b",
        r"\bISM\b",
        r"\bJOLTS\b",
        r"\bPCE\b",
        r"\bPPI\b",
        r"Average Hourly Earnings",
        r"Consumer Confidence",
        r"Consumer Price Index",
        r"Durable Goods",
        r"Employment Cost",
        r"Employment Situation",
        r"Federal Funds",
        r"Fed Interest Rate",
        r"Industrial Production",
        r"Initial Claims",
        r"Michigan Consumer",
        r"Non[- ]?Farm",
        r"Personal Consumption",
        r"Personal Income",
        r"Producer Price Index",
        r"Retail Sales",
        r"Unemployment Rate",
    ],
    "JPY": [
        r"\bBOJ\b",
        r"\bBoJ\b",
        r"\bCPI\b",
        r"\bGDP\b",
        r"Bank of Japan",
        r"Consumer Price Index",
        r"Industrial Production",
        r"Interest Rate",
        r"Monetary Policy",
        r"National Core CPI",
        r"Retail Sales",
        r"Tankan",
        r"Tokyo Core CPI",
        r"Trade Balance",
    ],
}


@dataclass(frozen=True)
class CalendarEvent:
    event_id: str
    event_time_utc: datetime
    country: str
    currency: str
    event_name: str
    impact: str
    actual: str
    forecast: str
    previous: str
    source: str


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def iter_dates(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def parse_gmt_time(value: str) -> datetime_time | None:
    text = (value or "").strip()
    if not text or text.upper() in {"ALL DAY", "TENTATIVE"}:
        return None
    match = re.fullmatch(r"(\d{1,2}):(\d{2})", text)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return datetime_time(hour, minute)


def is_high_impact(currency: str, event_name: str) -> bool:
    patterns = HIGH_IMPACT_PATTERNS.get(currency, [])
    return any(re.search(pattern, event_name, flags=re.IGNORECASE) for pattern in patterns)


def clean_value(value: str | None) -> str:
    text = (value or "").strip()
    return "" if text in {"&nbsp;", " "} else text


def event_id_for(day: date, currency: str, event_name: str, event_time_utc: datetime) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", event_name.lower()).strip("-")[:60]
    digest = hashlib.sha1(f"{event_time_utc.isoformat()}|{currency}|{event_name}".encode()).hexdigest()[:8]
    return f"{day.isoformat()}-{currency.lower()}-{slug}-{digest}"


def normalise_rows(day: date, rows: list[dict]) -> list[CalendarEvent]:
    events: list[CalendarEvent] = []
    seen: set[tuple[datetime, str, str]] = set()
    for row in rows:
        country = (row.get("country") or "").strip()
        currency = COUNTRY_TO_CURRENCY.get(country)
        if not currency:
            continue

        event_name = (row.get("eventName") or "").strip()
        if not event_name or not is_high_impact(currency, event_name):
            continue

        event_time = parse_gmt_time(row.get("gmt") or "")
        if event_time is None:
            continue

        event_time_utc = datetime.combine(day, event_time, tzinfo=timezone.utc)
        key = (event_time_utc, currency, event_name)
        if key in seen:
            continue
        seen.add(key)

        events.append(CalendarEvent(
            event_id=event_id_for(day, currency, event_name, event_time_utc),
            event_time_utc=event_time_utc,
            country=country,
            currency=currency,
            event_name=event_name,
            impact="HIGH",
            actual=clean_value(row.get("actual")),
            forecast=clean_value(row.get("consensus")),
            previous=clean_value(row.get("previous")),
            source="nasdaq_economic_calendar",
        ))
    return events


def fetch_day(
    day: date,
    cache_dir: Path,
    refresh: bool,
    timeout_seconds: int,
    retries: int,
    retry_sleep_seconds: float,
) -> list[dict]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{day.isoformat()}.json"
    if cache_file.exists() and not refresh:
        payload = json.loads(cache_file.read_text())
    else:
        query = urlencode({"date": day.isoformat()})
        request = Request(
            f"{NASDAQ_URL}?{query}",
            headers={
                "Accept": "application/json, text/plain, */*",
                "User-Agent": "Mozilla/5.0",
            },
        )
        last_error: Exception | None = None
        for attempt in range(1, retries + 2):
            try:
                with urlopen(request, timeout=timeout_seconds) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                break
            except (HTTPError, URLError, TimeoutError) as exc:
                last_error = exc
                if attempt > retries:
                    raise RuntimeError(
                        f"Failed to fetch Nasdaq calendar for {day.isoformat()} "
                        f"after {attempt} attempts: {exc}"
                    ) from exc
                sleep_for = retry_sleep_seconds * attempt
                print(
                    json.dumps({
                        "status": "RETRYING",
                        "date": day.isoformat(),
                        "attempt": attempt,
                        "max_attempts": retries + 1,
                        "sleep_seconds": sleep_for,
                        "error": str(exc),
                    })
                )
                time.sleep(sleep_for)
        else:
            raise RuntimeError(f"Failed to fetch Nasdaq calendar for {day.isoformat()}: {last_error}")
        cache_file.write_text(json.dumps(payload, indent=2, sort_keys=True))

    data = payload.get("data") if isinstance(payload, dict) else None
    rows = data.get("rows") if isinstance(data, dict) else None
    return rows if isinstance(rows, list) else []


def write_calendar(path: Path, events: list[CalendarEvent]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for event in sorted(events, key=lambda item: (item.event_time_utc, item.currency, item.event_name)):
            writer.writerow({
                "event_id": event.event_id,
                "event_time_utc": event.event_time_utc.isoformat().replace("+00:00", "Z"),
                "country": event.country,
                "currency": event.currency,
                "event_name": event.event_name,
                "impact": event.impact,
                "actual": event.actual,
                "forecast": event.forecast,
                "previous": event.previous,
                "source": event.source,
            })


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-date", required=True, help="First calendar date, YYYY-MM-DD.")
    parser.add_argument("--end-date", required=True, help="Last calendar date, YYYY-MM-DD.")
    parser.add_argument(
        "--output",
        default="data/macro_calendar/usd_jpy_events_2022_2025_nasdaq.csv",
        help="Output CSV path for the news guard.",
    )
    parser.add_argument(
        "--cache-dir",
        default="data/macro_calendar/cache/nasdaq",
        help="Per-day JSON cache directory. Existing cache files are reused.",
    )
    parser.add_argument("--sleep-seconds", type=float, default=0.25)
    parser.add_argument("--timeout-seconds", type=int, default=30)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--retry-sleep-seconds", type=float, default=5.0)
    parser.add_argument("--refresh-cache", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    start = parse_date(args.start_date)
    end = parse_date(args.end_date)
    if end < start:
        raise SystemExit("--end-date must be on or after --start-date")

    cache_dir = Path(args.cache_dir)
    all_events: list[CalendarEvent] = []
    fetched_days = 0
    cache_hits = 0
    for day in iter_dates(start, end):
        cache_file = cache_dir / f"{day.isoformat()}.json"
        used_cache = cache_file.exists() and not args.refresh_cache
        rows = fetch_day(
            day,
            cache_dir,
            args.refresh_cache,
            args.timeout_seconds,
            args.retries,
            args.retry_sleep_seconds,
        )
        all_events.extend(normalise_rows(day, rows))
        fetched_days += 1
        cache_hits += int(used_cache)
        if not used_cache and args.sleep_seconds > 0:
            time.sleep(args.sleep_seconds)

    output = Path(args.output)
    write_calendar(output, all_events)
    print(json.dumps({
        "output": str(output),
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "calendar_days": fetched_days,
        "cache_hits": cache_hits,
        "events_written": len(all_events),
        "source": "nasdaq_economic_calendar",
        "note": "Times are taken from Nasdaq's gmt field and written as UTC.",
    }, indent=2))


if __name__ == "__main__":
    main()
