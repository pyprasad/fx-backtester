import numpy as np
import polars as pl

from src.stress.equity_simulator import EquitySimulator
from src.stress.sequence_stress import sequence_stress_rows
from src.stress.trade_sampler import TradeSampler


def test_sequence_stress_contains_worst_first():
    trades = pl.DataFrame({"pnl_r": [1.0, -1.0, 2.0], "net_pnl": [1.0, -1.0, 2.0]})
    rows = sequence_stress_rows(trades, TradeSampler(np.random.default_rng(1)), EquitySimulator(100, 1))
    assert {row["scenario_name"] for row in rows} >= {"historical_order", "worst_trades_first"}
