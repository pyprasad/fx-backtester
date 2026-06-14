import numpy as np
import polars as pl


class TradeSampler:
    def __init__(self, rng: np.random.Generator):
        self.rng = rng

    def shuffle_without_replacement(self, trades: pl.DataFrame) -> pl.DataFrame:
        return trades[self.rng.permutation(trades.height)]

    def bootstrap_with_replacement(self, trades: pl.DataFrame, n: int | None = None) -> pl.DataFrame:
        return trades[self.rng.integers(0, trades.height, n or trades.height)]

    def block_bootstrap(self, trades: pl.DataFrame, block_size: int, n: int | None = None) -> pl.DataFrame:
        n = n or trades.height
        indices = []
        while len(indices) < n:
            start = int(self.rng.integers(0, max(1, trades.height - block_size + 1)))
            indices.extend(range(start, min(start + block_size, trades.height)))
        return trades[indices[:n]]

    def remove_random_trades(self, trades: pl.DataFrame, missed_rate: float) -> pl.DataFrame:
        remove = round(trades.height * missed_rate)
        keep = self.rng.choice(trades.height, trades.height - remove, replace=False)
        return trades[sorted(keep)]

    def remove_best_trades(self, trades: pl.DataFrame, missed_rate: float) -> pl.DataFrame:
        remove = round(trades.height * missed_rate)
        ranked = trades.with_row_index("_row").sort("pnl_r", descending=True)
        removed = ranked.head(remove)["_row"].to_list()
        return trades.with_row_index("_row").filter(~pl.col("_row").is_in(removed)).drop("_row")

    def remove_worst_trades(self, trades: pl.DataFrame, missed_rate: float) -> pl.DataFrame:
        remove = round(trades.height * missed_rate)
        ranked = trades.with_row_index("_row").sort("pnl_r")
        removed = ranked.head(remove)["_row"].to_list()
        return trades.with_row_index("_row").filter(~pl.col("_row").is_in(removed)).drop("_row")

    def worst_trades_first(self, trades: pl.DataFrame) -> pl.DataFrame:
        return trades.sort("pnl_r")

    def best_trades_first(self, trades: pl.DataFrame) -> pl.DataFrame:
        return trades.sort("pnl_r", descending=True)

    def alternating_loss_clusters(self, trades: pl.DataFrame) -> pl.DataFrame:
        losses = trades.filter(pl.col("pnl_r") <= 0).sort("pnl_r")
        wins = trades.filter(pl.col("pnl_r") > 0).sort("pnl_r", descending=True)
        rows, li, wi = [], 0, 0
        while li < losses.height or wi < wins.height:
            for _ in range(3):
                if li < losses.height:
                    rows.append(losses.row(li, named=True))
                    li += 1
            if wi < wins.height:
                rows.append(wins.row(wi, named=True))
                wi += 1
        return pl.DataFrame(rows, schema=trades.schema)
