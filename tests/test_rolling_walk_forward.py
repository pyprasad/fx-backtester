from datetime import datetime, timezone

from src.walk_forward.rolling_walk_forward import analyze_rolling
from src.walk_forward.window_backtest import WindowBacktestRunner
from src.walk_forward.window_builder import build_rolling_windows


def test_rolling_summary(stability_trades):
    windows = build_rolling_windows(
        {"definitions": [{"name": "train_12m_test_3m", "train_months": 12, "test_months": 3,
                          "step_months": 3}]},
        datetime(2022, 1, 1, tzinfo=timezone.utc), datetime(2023, 12, 31, tzinfo=timezone.utc),
    )
    details, summary = analyze_rolling(windows, WindowBacktestRunner(
        stability_trades, 10_000, {"min_train_trades_warning": 1, "min_test_trades_warning": 1}
    ))
    assert details["train_12m_test_3m"].height == 4
    assert summary[0, "positive_test_window_percent"] == 25
