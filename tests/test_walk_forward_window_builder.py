from datetime import datetime, timezone

from src.walk_forward.window_builder import (
    WalkForwardWindow,
    build_rolling_windows,
    validate_windows,
)


def test_valid_and_overlapping_windows():
    valid = WalkForwardWindow("a", "anchored", "a", datetime(2022, 1, 1, tzinfo=timezone.utc),
                              datetime(2022, 12, 31, tzinfo=timezone.utc),
                              datetime(2023, 1, 1, tzinfo=timezone.utc),
                              datetime(2023, 12, 31, tzinfo=timezone.utc))
    overlap = WalkForwardWindow("b", "anchored", "b", valid.train_start, valid.test_start,
                                valid.train_end, valid.test_end)
    assert validate_windows([valid]) == []
    assert validate_windows([overlap])


def test_rolling_window_generation():
    config = {"definitions": [
        {"name": "train_12m_test_3m", "train_months": 12, "test_months": 3, "step_months": 3},
        {"name": "train_24m_test_6m", "train_months": 24, "test_months": 6, "step_months": 6},
    ]}
    windows = build_rolling_windows(
        config, "2022-01-01T00:00:00+00:00", "2025-12-31T23:59:59+00:00"
    )
    twelve = [window for window in windows if window.name == "train_12m_test_3m"]
    twenty_four = [window for window in windows if window.name == "train_24m_test_6m"]
    assert len(twelve) == 12
    assert len(twenty_four) == 4
    assert all(window.test_end.year <= 2025 for window in windows)
    assert validate_windows(
        windows,
        datetime(2022, 1, 1, tzinfo=timezone.utc),
        datetime(2025, 12, 31, tzinfo=timezone.utc),
    ) == []
