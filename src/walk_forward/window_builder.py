from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass(frozen=True)
class WalkForwardWindow:
    window_id: str
    window_type: str
    name: str
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    train_months: int | None = None
    test_months: int | None = None
    step_months: int | None = None
    notes: str = ""


def _utc(value) -> datetime:
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _add_months(value: datetime, months: int) -> datetime:
    index = value.year * 12 + value.month - 1 + months
    return value.replace(year=index // 12, month=index % 12 + 1)


def build_anchored_windows(config: dict) -> list[WalkForwardWindow]:
    def inclusive_end(value):
        parsed = _utc(value)
        if parsed.hour == 23 and parsed.minute == 59 and parsed.second == 59 and parsed.microsecond == 0:
            parsed += timedelta(microseconds=999_999)
        return parsed

    return [
        WalkForwardWindow(
            window_id=f"anchored_{index:02d}", window_type="anchored", name=item["name"],
            train_start=_utc(item["train_start"]), train_end=inclusive_end(item["train_end"]),
            test_start=_utc(item["test_start"]), test_end=inclusive_end(item["test_end"]),
            notes="Fixed-parameter anchored out-of-sample window",
        )
        for index, item in enumerate(config.get("windows", []), 1)
    ]


def build_rolling_windows(config: dict, available_start, available_end) -> list[WalkForwardWindow]:
    available_start = _utc(available_start).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    available_end = _utc(available_end)
    available_end_exclusive = available_end.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    windows = []
    for definition in config.get("definitions", []):
        start = available_start
        index = 1
        while True:
            test_start = _add_months(start, definition["train_months"])
            test_end_exclusive = _add_months(test_start, definition["test_months"])
            test_end = test_end_exclusive - timedelta(microseconds=1)
            if test_end_exclusive > available_end_exclusive:
                break
            windows.append(WalkForwardWindow(
                window_id=f"{definition['name']}_{index:02d}", window_type="rolling",
                name=definition["name"], train_start=start,
                train_end=test_start - timedelta(microseconds=1), test_start=test_start,
                test_end=test_end, train_months=definition["train_months"],
                test_months=definition["test_months"], step_months=definition["step_months"],
                notes="Fixed-parameter rolling out-of-sample window",
            ))
            start = _add_months(start, definition["step_months"])
            index += 1
    return sorted(windows, key=lambda window: (window.name, window.test_start))


def validate_windows(windows: list[WalkForwardWindow], available_start=None, available_end=None) -> list[str]:
    errors = []
    lower = _utc(available_start) if available_start else None
    upper = _utc(available_end) if available_end else None
    if upper and upper.hour == 0 and upper.minute == 0 and upper.second == 0 and upper.microsecond == 0:
        upper += timedelta(days=1) - timedelta(microseconds=1)
    for window in windows:
        if window.train_start >= window.train_end:
            errors.append(f"{window.window_id}: train_start must be before train_end")
        if window.test_start >= window.test_end:
            errors.append(f"{window.window_id}: test_start must be before test_end")
        if window.train_end >= window.test_start:
            errors.append(f"{window.window_id}: train and test periods overlap")
        if lower and window.test_start < lower:
            errors.append(f"{window.window_id}: test period starts before available data")
        if upper and window.test_end > upper:
            errors.append(f"{window.window_id}: test period ends after available data")
    return errors
