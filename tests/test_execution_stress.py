import polars as pl

from src.stress.execution_stress import apply_friday_close_slippage, apply_slippage, apply_spread_multiplier


def _trades():
    return pl.DataFrame({
        "pnl_r": [1.0, 1.0], "initial_risk_pips": [10.0, 10.0],
        "spread_pips_at_entry": [1.0, 1.0], "spread_pips_at_exit": [1.0, 1.0],
        "exit_reason": ["weekend_force_close", "take_profit"],
    })


def test_execution_costs_reduce_r():
    assert apply_slippage(_trades(), 1, "both")["pnl_r"][0] == .8
    assert apply_spread_multiplier(_trades(), 2, "both")["pnl_r"][0] == .8
    friday = apply_friday_close_slippage(_trades(), 1)
    assert friday["pnl_r"].to_list() == [.9, 1.0]
