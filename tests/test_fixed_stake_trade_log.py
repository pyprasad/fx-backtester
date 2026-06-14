import csv
from datetime import datetime, timezone

from src.execution.trade import Trade
from src.reporting.csv_report import write_csv_reports


def test_fixed_stake_trade_log_and_specialized_reports(tmp_path):
    trade = Trade(
        "t", "s", "USDJPY", "SHORT", datetime.now(timezone.utc), datetime.now(timezone.utc),
        160.2, 160.0, 160.25, 160.25, 160.0, 4, 0.2, 0.8, 0.8, 4, 0, 0, 1,
        1 / 3600, 1 / 86400, "take_profit", 0.5, 0.5,
        position_sizing_mode="fixed_spread_bet_stake", stake_per_pip_gbp=0.04,
        pnl_pips=20, pnl_gbp=0.8, planned_loss_gbp=0.2,
    )
    metrics = {
        "starting_balance": 10000, "ending_balance": 10000.8, "total_return_percent": 0.008,
        "position_sizing_mode": "fixed_spread_bet_stake", "net_profit_gbp": 0.8,
        "total_pips": 20, "gross_profit_gbp": 0.8, "gross_loss_gbp": 0,
        "profit_factor": 0, "total_trades": 1, "max_drawdown_gbp": 0,
        "max_drawdown_percent": 0, "stake_per_pip_gbp": 0.04,
        "estimated_loss_at_3pip_stop_gbp": 0.12, "estimated_loss_at_5pip_stop_gbp": 0.2,
        "estimated_loss_at_10pip_stop_gbp": 0.4, "estimated_loss_at_20pip_stop_gbp": 0.8,
        "average_trade_pips": 20, "average_win_pips": 20, "average_loss_pips": 0,
        "best_trade_pips": 20, "worst_trade_pips": 20,
    }
    write_csv_reports(tmp_path, [trade], metrics, [])
    with (tmp_path / "trade_log.csv").open() as handle:
        fields = next(csv.DictReader(handle)).keys()
    assert {"pnl_pips", "pnl_gbp", "stake_per_pip_gbp", "planned_loss_gbp"} <= set(fields)
    assert (tmp_path / "fixed_stake_summary.csv").exists()
    assert (tmp_path / "pips_summary.csv").exists()
