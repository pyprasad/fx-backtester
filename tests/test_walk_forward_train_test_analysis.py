from datetime import datetime, timezone

from src.walk_forward.train_test_analysis import calculate_period_metrics, filter_trades


def test_filtering_metrics_and_no_future_leakage(stability_trades):
    train = filter_trades(stability_trades, datetime(2022, 1, 1, tzinfo=timezone.utc),
                          datetime(2022, 12, 31, 23, 59, tzinfo=timezone.utc))
    test = filter_trades(stability_trades, datetime(2023, 1, 1, tzinfo=timezone.utc),
                         datetime(2023, 12, 31, 23, 59, tzinfo=timezone.utc))
    assert train["trade_id"].to_list() == ["a", "b"]
    assert test["trade_id"].to_list() == ["c", "d"]
    metrics = calculate_period_metrics(train, train["entry_timestamp_utc"].min(),
                                       train["entry_timestamp_utc"].max(), 10_000, 3)
    assert metrics["net_profit"] == 60
    assert metrics["win_rate"] == 50
    assert metrics["profit_factor"] == 2.5
    assert metrics["low_sample_warning"] is True
