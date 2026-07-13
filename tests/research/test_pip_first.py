from datetime import datetime, timezone

from src.execution.trade import Trade
from src.research.pip_first import (
    calculate_pip_metrics,
    trade_pips,
    write_pip_first_report,
    write_pip_first_stress_report,
)


def _trade(**overrides):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    values = {
        "trade_id": "t1",
        "signal_id": "s1",
        "symbol": "USDJPY",
        "direction": "LONG",
        "entry_timestamp_utc": now,
        "exit_timestamp_utc": now,
        "entry_price": 160.0,
        "exit_price": 160.5,
        "initial_stop": 159.8,
        "final_stop": 159.8,
        "target_price": 160.8,
        "size": 1,
        "risk_amount": 20,
        "gross_pnl": 50,
        "net_pnl": 50,
        "pnl_r": 2.5,
        "max_favourable_excursion": 0.5,
        "max_adverse_excursion": 0,
        "duration_seconds": 1,
        "duration_hours": 1 / 3600,
        "duration_days": 1 / 86400,
        "exit_reason": "take_profit",
        "spread_pips_at_entry": 0.2,
        "spread_pips_at_exit": 0.2,
    }
    values.update(overrides)
    return Trade(**values)


def test_trade_pips_preserves_direction_and_partial_exits():
    long_trade = _trade(
        partial_exits=[{"price": 160.2, "fraction": 0.5}],
        exit_price=160.5,
    )
    short_trade = _trade(
        direction="SHORT",
        entry_price=160.0,
        exit_price=159.7,
        initial_stop=160.2,
        target_price=159.2,
    )

    assert round(trade_pips(long_trade), 6) == 35
    assert round(trade_pips(short_trade), 6) == 30


def test_calculate_pip_metrics_includes_fixed_pip_value_outcomes():
    trades = [_trade(), _trade(entry_price=160.0, exit_price=159.8, net_pnl=-20, pnl_r=-1)]

    metrics = calculate_pip_metrics(trades, pip_values=[1.0], starting_balance=1000)

    assert metrics["net_pips"] == 30
    assert metrics["fixed_1_0_per_pip_net_pnl"] == 30
    assert metrics["fixed_1_0_per_pip_ending_balance"] == 1030
    assert metrics["max_pip_drawdown"] == 20


def test_write_pip_first_report_from_backtest_trade_log(tmp_path):
    run = tmp_path / "run_a"
    run.mkdir()
    (run / "trade_log.csv").write_text(
        "trade_id,direction,entry_price,exit_price,initial_stop,target_price,partial_exits,exit_timestamp_utc,session\n"
        "t1,LONG,160.0,160.5,159.8,160.8,[],2026-01-01T00:00:00+00:00,London\n"
    )

    output = write_pip_first_report([run], tmp_path / "pip_report", pip_values=[1.0], starting_balance=1000)

    assert (output / "pip_first_summary.csv").exists()
    assert (output / "pip_first_report.html").exists()
    assert (output / "run_a" / "pip_trade_log.csv").exists()


def test_trade_pips_parses_csv_partial_exits_with_datetime_repr():
    row = {
        "direction": "LONG",
        "entry_price": "160.0",
        "exit_price": "160.5",
        "initial_stop": "159.8",
        "target_price": "160.8",
        "partial_exits": (
            "[{'timestamp': datetime.datetime(2026, 1, 1, 0, 0, "
            "tzinfo=zoneinfo.ZoneInfo(key='UTC')), 'price': 160.2, 'fraction': 0.5}]"
        ),
    }

    assert round(trade_pips(row), 6) == 35


def test_write_pip_first_stress_report(tmp_path):
    run = tmp_path / "run_a"
    run.mkdir()
    (run / "trade_log.csv").write_text(
        "trade_id,direction,entry_price,exit_price,initial_stop,target_price,partial_exits,exit_timestamp_utc,session\n"
        "t1,LONG,160.0,160.5,159.8,160.8,[],2026-01-01T00:00:00+00:00,London\n"
        "t2,LONG,160.0,159.8,159.8,160.8,[],2026-01-02T00:00:00+00:00,London\n"
    )

    output = write_pip_first_stress_report(
        [run],
        tmp_path / "stress",
        pip_values=[1.0],
        iterations=20,
        slippage_pips=[0.0],
        missed_trade_rates=[0.0],
    )

    summary = output / "pip_first_stress_summary.csv"
    assert summary.exists()
    assert (output / "pip_first_stress_report.html").exists()
    assert "bootstrap" in summary.read_text()
