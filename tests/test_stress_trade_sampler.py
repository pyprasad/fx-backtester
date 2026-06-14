import numpy as np
import polars as pl

from src.stress.trade_sampler import TradeSampler


def _trades():
    return pl.DataFrame({"id": list(range(10)), "pnl_r": [-3, -2, -1, 0, 1, 2, 3, 4, 5, 6]})


def test_shuffle_bootstrap_and_removals():
    trades, sampler = _trades(), TradeSampler(np.random.default_rng(42))
    shuffled = sampler.shuffle_without_replacement(trades)
    assert sorted(shuffled["id"].to_list()) == list(range(10))
    assert shuffled["id"].to_list() != list(range(10))
    boot = sampler.bootstrap_with_replacement(trades)
    assert boot.height == trades.height
    assert sampler.remove_random_trades(trades, .1).height == 9
    assert sampler.remove_best_trades(trades, .2)["id"].to_list() == list(range(8))
    assert sampler.remove_worst_trades(trades, .2)["id"].to_list() == list(range(2, 10))
    assert sampler.worst_trades_first(trades)["pnl_r"].to_list() == sorted(trades["pnl_r"])


def test_block_bootstrap_length():
    result = TradeSampler(np.random.default_rng(1)).block_bootstrap(_trades(), 3, 10)
    assert result.height == 10
