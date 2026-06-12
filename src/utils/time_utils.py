from datetime import datetime
from zoneinfo import ZoneInfo


def to_london(value: datetime) -> datetime:
    return value.astimezone(ZoneInfo("Europe/London"))
