from datetime import datetime, timezone

from src.execution.trade import Trade
from src.reporting.metrics import calculate_metrics


def test_report_metrics_are_rounded_for_display():
    now = datetime.now(timezone.utc)
    trade = Trade(
        "t", "s", "USDJPY", "SHORT", now, now, 103.1, 103.0, 103.2, 103.2,
        102.7, 1, 25, 24.740353905043715, 24.740353905043715, 0.9896141562017486,
        0.1, -0.1, 1, 1 / 3600, 1 / 86400, "take_profit",
        0.19999999999953388, 0.20000000000095497,
    )
    metrics = calculate_metrics([trade], 10000)
    assert metrics["ending_balance"] == 10024.74
    assert metrics["average_r"] == 0.9896
    assert metrics["average_spread_pips_at_entry"] == 0.2
