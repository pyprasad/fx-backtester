import polars as pl

from .train_test_analysis import calculate_period_metrics, filter_trades


class WindowBacktestRunner:
    """Filter a deterministic fixed-parameter baseline trade log into train/test periods."""

    def __init__(self, trades: pl.DataFrame, starting_balance: float, minimums: dict):
        self.trades = trades
        self.starting_balance = starting_balance
        self.minimums = minimums

    def run_window(self, window) -> tuple[dict, dict]:
        train = filter_trades(self.trades, window.train_start, window.train_end)
        test = filter_trades(self.trades, window.test_start, window.test_end)
        return (
            calculate_period_metrics(
                train, window.train_start, window.train_end, self.starting_balance,
                self.minimums.get("min_train_trades_warning", 30),
            ),
            calculate_period_metrics(
                test, window.test_start, window.test_end, self.starting_balance,
                self.minimums.get("min_test_trades_warning", 10),
            ),
        )
