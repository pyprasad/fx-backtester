import csv
from pathlib import Path
from types import SimpleNamespace

import yaml

from src.backtest.weekend_policy_runner import WeekendPolicyVariantRunner, score_variant


def test_scoring_verdicts():
    base = {
        "total_return_percent": 30, "max_drawdown_percent": 5, "profit_factor": 1.6,
        "average_r": 0.4, "trades_loss_beyond_2_5r_count": 0, "trades_loss_beyond_5r_count": 0,
    }
    assert score_variant({**base, "worst_trade_r": -14})[1] == "REJECT"
    assert score_variant({**base, "worst_trade_r": -1.5})[1] == "STRONG_PASS"


def test_variant_runner_writes_comparison(monkeypatch, tmp_path: Path):
    variants = tmp_path / "variants.yaml"
    variants.write_text(yaml.safe_dump({"variants": [
        {"name": "baseline_allow_weekend", "description": "baseline", "weekend_policy": {"enabled": False}},
        {"name": "safe", "description": "safe", "weekend_policy": {"enabled": True}},
    ]}))
    monkeypatch.setattr("src.backtest.weekend_policy_runner.load_strategy_config", lambda _path: SimpleNamespace(
        data={}, weekend_policy={}, reporting={}, base_dir=tmp_path,
    ))

    def fake_backtest(config, output_override):
        output_override.mkdir(parents=True)
        with (output_override / "weekend_policy_summary.csv").open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=[
                "weekend_held_trades", "weekend_held_losses", "weekend_force_closes",
                "weekend_partial_reductions", "weekend_stop_tightens",
                "friday_cutoff_signal_rejections", "sunday_open_signal_rejections",
            ])
            writer.writeheader()
            writer.writerow({key: 0 for key in writer.fieldnames})
        metrics = {
            "starting_balance": 10000, "ending_balance": 11000, "total_return_percent": 10,
            "net_profit": 1000, "total_trades": 1, "winning_trades": 1, "losing_trades": 0,
            "win_rate": 100, "profit_factor": 2, "max_drawdown_percent": 1,
            "max_drawdown_amount": 100, "average_r": 1, "expectancy_r": 1,
            "average_win_r": 1, "average_loss_r": 0, "best_trade_r": 1, "worst_trade_r": -1,
            "average_trade_duration": 24, "median_trade_duration": 24, "stop_loss_exit_count": 0,
            "take_profit_exit_count": 1, "trailing_stop_exit_count": 0,
            "weekend_force_close_exit_count": 0, "weekend_losing_trade_close_exit_count": 0,
            "weekend_profit_threshold_close_exit_count": 0,
        }
        return [], metrics, output_override

    monkeypatch.setattr("src.backtest.weekend_policy_runner.run_backtest", fake_backtest)
    output = WeekendPolicyVariantRunner("base.yaml", variants, tmp_path / "ticks", tmp_path / "candles", tmp_path / "out").run_all_variants()
    assert (output / "weekend_policy_comparison.csv").exists()
    assert (output / "weekend_policy_comparison.html").exists()
