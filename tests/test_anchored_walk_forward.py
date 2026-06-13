from datetime import datetime, timezone

from src.walk_forward.anchored_walk_forward import analyze_windows
from src.walk_forward.window_backtest import WindowBacktestRunner
from src.walk_forward.window_builder import WalkForwardWindow


def test_anchored_verdict_and_decay(stability_trades):
    window = WalkForwardWindow(
        "a", "anchored", "test", datetime(2022, 1, 1, tzinfo=timezone.utc),
        datetime(2022, 12, 31, 23, 59, tzinfo=timezone.utc),
        datetime(2023, 1, 1, tzinfo=timezone.utc),
        datetime(2023, 12, 31, 23, 59, tzinfo=timezone.utc),
    )
    result = analyze_windows([window], WindowBacktestRunner(
        stability_trades, 10_000, {"min_train_trades_warning": 1, "min_test_trades_warning": 1}
    ))
    assert result[0, "test_trades"] == 2
    assert result[0, "test_positive_flag"]
    assert result[0, "verdict"] in {"PASS", "STRONG"}
