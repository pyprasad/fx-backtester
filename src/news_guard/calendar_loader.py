import csv
from datetime import datetime, timezone
from pathlib import Path

from .models import EconomicEvent


def _parse_utc(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _blank_to_none(value: str | None) -> str | None:
    return value if value not in {None, ""} else None


def load_economic_events(
    calendar_file: str | Path,
    affected_currencies: list[str],
    impact_levels: list[str],
) -> list[EconomicEvent]:
    path = Path(calendar_file)
    if not path.exists():
        raise FileNotFoundError(f"News guard calendar file not found: {path}")
    if not path.read_text().strip():
        return []

    currencies = {item.upper() for item in affected_currencies}
    impacts = {item.upper() for item in impact_levels}
    events = []
    with path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            currency = (row.get("currency") or "").upper()
            impact = (row.get("impact") or "").upper()
            if currencies and currency not in currencies:
                continue
            if impacts and impact not in impacts:
                continue
            events.append(EconomicEvent(
                event_id=row["event_id"],
                event_time_utc=_parse_utc(row["event_time_utc"]),
                country=row.get("country", ""),
                currency=currency,
                event_name=row.get("event_name", ""),
                impact=impact,
                actual=_blank_to_none(row.get("actual")),
                forecast=_blank_to_none(row.get("forecast")),
                previous=_blank_to_none(row.get("previous")),
                source=_blank_to_none(row.get("source")),
            ))
    return sorted(events, key=lambda event: event.event_time_utc)

