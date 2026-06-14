import polars as pl

from src.stress.equity_simulator import EquitySimulator


def test_r_compounding_drawdown_and_losses():
    result = EquitySimulator(10000, 1).simulate(pl.DataFrame({"pnl_r": [1.0, -2.0, -1.0, 1.0]}))
    assert result["ending_balance"] == 9897.0102
    assert result["max_drawdown_percent"] > 2.9
    assert result["consecutive_losses_max"] == 2
