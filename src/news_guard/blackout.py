from datetime import datetime, timedelta, timezone

from .models import EconomicEvent


def _as_utc(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc)


def is_news_blackout(
    timestamp_utc: datetime,
    events: list[EconomicEvent],
    before_minutes: int,
    after_minutes: int,
) -> tuple[bool, EconomicEvent | None]:
    timestamp = _as_utc(timestamp_utc)
    before = timedelta(minutes=before_minutes)
    after = timedelta(minutes=after_minutes)
    for event in events:
        event_time = _as_utc(event.event_time_utc)
        if event_time - before <= timestamp <= event_time + after:
            return True, event
    return False, None

