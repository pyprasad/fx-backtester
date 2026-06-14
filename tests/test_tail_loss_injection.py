import polars as pl

from src.stress.equity_simulator import EquitySimulator


def test_tail_loss_changes_return():
    simulator = EquitySimulator(10000, 1)
    baseline = simulator.simulate(pl.DataFrame({"pnl_r": [1.0, 1.0]}))
    stressed = simulator.simulate(pl.DataFrame({"pnl_r": [1.0, -5.0, 1.0]}))
    assert stressed["total_return_percent"] < baseline["total_return_percent"]
