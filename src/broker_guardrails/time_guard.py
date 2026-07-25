from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from .broker_rules import GuardrailDecision


@dataclass(frozen=True)
class MarketHibernateWindow:
    enabled: bool
    reason: str | None = None
    resume_at_utc: datetime | None = None
    resume_at_local: datetime | None = None
    timestamp_local: datetime | None = None


def weekend_market_hibernate_window(
    timestamp_utc: datetime,
    *,
    timezone_name: str = "Europe/London",
    friday_close: str = "22:00",
    sunday_resume: str = "23:00",
) -> MarketHibernateWindow:
    """Return the weekend hibernate window for the live FX bot."""
    if timestamp_utc.tzinfo is None:
        timestamp_utc = timestamp_utc.replace(tzinfo=timezone.utc)
    local_tz = ZoneInfo(timezone_name)
    local = timestamp_utc.astimezone(local_tz)
    close_time = time.fromisoformat(friday_close)
    resume_time = time.fromisoformat(sunday_resume)

    if local.weekday() == 4 and local.time() >= close_time:
        days_until_sunday = 6 - local.weekday()
    elif local.weekday() == 5:
        days_until_sunday = 1
    elif local.weekday() == 6 and local.time() < resume_time:
        days_until_sunday = 0
    else:
        return MarketHibernateWindow(enabled=False, timestamp_local=local)

    resume_date = local.date() + timedelta(days=days_until_sunday)
    resume_local = datetime.combine(resume_date, resume_time, local_tz)
    return MarketHibernateWindow(
        enabled=True,
        reason="WEEKEND_MARKET_HIBERNATE",
        resume_at_utc=resume_local.astimezone(timezone.utc),
        resume_at_local=resume_local,
        timestamp_local=local,
    )


def validate_entry_time(timestamp_utc, settings: dict,
                        decision: GuardrailDecision | None = None) -> GuardrailDecision:
    decision = decision or GuardrailDecision()
    guard = settings["entry_time_guard"]
    local = timestamp_utc.astimezone(ZoneInfo(guard["timezone"]))
    decision.timestamp_utc, decision.timestamp_local = timestamp_utc, local
    # The configured cutoff is inclusive: signals at 21:30 UK time are blocked.
    if guard.get("enabled") and local.time() >= time.fromisoformat(guard["block_new_entries_after"]):
        decision.reject("REJECT_AFTER_FUNDING_ENTRY_CUTOFF")
    return decision
