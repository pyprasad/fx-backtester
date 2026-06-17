from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class EconomicEvent:
    event_id: str
    event_time_utc: datetime
    country: str
    currency: str
    event_name: str
    impact: str
    actual: str | None = None
    forecast: str | None = None
    previous: str | None = None
    source: str | None = None

