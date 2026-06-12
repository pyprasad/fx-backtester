from pathlib import Path
from datetime import datetime, timedelta, timezone

import polars as pl

from src.forensics.forensic_report import write_forensic_report
from src.forensics.trade_forensics import TradeForensicsEngine


def test_forensic_report_generation(tmp_path: Path):
    summary = {"final_status": "WARNING", "worst_trade_r": -3, "critical_flag_count": 0, "warning_flag_count": 1}
    worst = [{"trade_id": "t", "actual_pnl_r": -3, "integrity_flags": ["FLAG_LOSS_BEYOND_EXPECTED_R"]}]
    flags = [{"trade_id": "t", "flag": "FLAG_LOSS_BEYOND_EXPECTED_R"}]
    write_forensic_report(tmp_path, summary, worst, flags)
    assert (tmp_path / "forensic_report.html").exists()
    assert (tmp_path / "forensic_summary.csv").exists()
    assert (tmp_path / "forensic_summary.json").exists()


def test_forensic_engine_generates_required_reports(tmp_path: Path, strategy_config):
    now = datetime(2025, 1, 6, 10, tzinfo=timezone.utc)
    tick_path = tmp_path / "ticks.parquet"
    pl.DataFrame({
        "timestamp_utc": [now, now + timedelta(seconds=1)],
        "bid": [150.0, 150.08], "ask": [150.02, 150.1],
        "mid": [150.01, 150.09], "spread_pips": [2.0, 2.0],
    }).write_parquet(tick_path)
    trade = {
        "trade_id": "t", "signal_id": "s", "symbol": "USDJPY", "direction": "SHORT",
        "entry_timestamp_utc": now, "exit_timestamp_utc": now + timedelta(seconds=1),
        "entry_price": 149.998, "exit_price": 150.102, "initial_stop": 150.1,
        "final_stop": 150.1, "target_price": 149.6, "risk_amount": 25.0,
        "net_pnl": -25.49, "pnl_r": -1.0196, "exit_reason": "stop_loss",
        "spread_pips_at_entry": 2.0, "spread_pips_at_exit": 2.0, "partial_exits": "[]",
        "duration_hours": 1 / 3600, "duration_days": 1 / 86400,
    }
    run = tmp_path / "run"
    engine = TradeForensicsEngine(strategy_config, [trade], tick_path, tmp_path, run)
    summary = engine.run()
    assert summary["audited_trades"] == 1
    assert (run / "forensics" / "stop_audit.csv").exists()
    assert (run / "forensics" / "forensic_report.html").exists()
