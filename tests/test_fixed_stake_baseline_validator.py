from datetime import datetime, timezone

from src.config.config_loader import load_strategy_config
from src.execution.trade import Trade
from src.reporting.csv_report import write_csv_reports
from src.reporting.metrics import calculate_metrics
from src.validation.fixed_stake_baseline_validator import validate_fixed_stake_baseline
from src.validation.weekend_exposure_audit import weekend_exposure_audit


def _trade(crossed=False, old_gap=False):
    entry = datetime(2025, 1, 3, 20, tzinfo=timezone.utc)
    exit_at = datetime(2025, 1, 5, 21, tzinfo=timezone.utc) if crossed else datetime(
        2025, 1, 3, 20, 30, tzinfo=timezone.utc
    )
    pips, pnl_r = (-205.1, -14.7708) if old_gap else (20, 1)
    return Trade(
        "t", "s", "USDJPY", "SHORT", entry, exit_at, 160, 159.8, 160.2, 160.2, 159,
        4, 0.8, pips * 0.04, pips * 0.04, pnl_r, 0, 0, 1, 1, 1 / 24,
        "stop_loss" if crossed else "weekend_force_close", 1, 1, held_over_weekend=crossed,
        position_sizing_mode="fixed_spread_bet_stake", stake_per_pip_gbp=0.04,
        pnl_pips=pips, pnl_gbp=pips * 0.04, planned_loss_gbp=0.8,
    )


def _metrics(trade):
    return {
        "starting_balance": 10000, "ending_balance": 10000 + trade.pnl_gbp,
        "net_profit_gbp": trade.pnl_gbp, "total_pips": trade.pnl_pips,
        "worst_trade_r": trade.pnl_r, "position_sizing_mode": "fixed_spread_bet_stake",
    }


def test_validator_passes_clean_final_baseline_and_summary_contains_metadata(tmp_path):
    config, trade = load_strategy_config(
        "config/strategy.usdjpy.fx_swing_trend_reclaim.fixed_004.yaml"
    ), _trade()
    metrics = calculate_metrics([trade], 10000)
    validation = validate_fixed_stake_baseline(config, [trade], metrics, weekend_exposure_audit([trade]))
    assert validation["validation_status"] == "PASS"
    metrics.update(validation)
    write_csv_reports(tmp_path, [trade], metrics, [])
    assert "weekend_policy_enabled" in (tmp_path / "strategy_summary.json").read_text()
    assert "validation_status" in (tmp_path / "strategy_summary.json").read_text()


def test_validator_rejects_old_weekend_gap():
    config, trade = load_strategy_config(
        "config/strategy.usdjpy.fx_swing_trend_reclaim.fixed_004.yaml"
    ), _trade(crossed=True, old_gap=True)
    validation = validate_fixed_stake_baseline(config, [trade], _metrics(trade), weekend_exposure_audit([trade]))
    assert validation["validation_status"] == "FAILED_VALIDATION"
    assert "OLD_WEEKEND_GAP_LOSS_PRESENT" in validation["validation_errors"]
