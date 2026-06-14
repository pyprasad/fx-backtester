from datetime import datetime, timezone

from src.execution.trade import Trade
from src.validation.weekend_exposure_audit import weekend_exposure_audit


def _trade(entry, exit_at, reason, held=False, pnl_r=-1, pnl_pips=-10):
    return Trade(
        "t", "s", "USDJPY", "SHORT", entry, exit_at, 160, 160.1, 160.2, 160.2, 159,
        4, 0.8, -0.4, -0.4, pnl_r, 0, 0, 1, 1, 1 / 24, reason, 1, 1,
        held_over_weekend=held, position_sizing_mode="fixed_spread_bet_stake",
        stake_per_pip_gbp=0.04, pnl_pips=pnl_pips, pnl_gbp=pnl_pips * 0.04,
    )


def test_weekend_crossing_is_flagged_and_force_close_is_clean():
    friday = datetime(2025, 1, 3, 20, tzinfo=timezone.utc)
    crossed = _trade(friday, datetime(2025, 1, 5, 21, tzinfo=timezone.utc), "stop_loss", True)
    closed = _trade(friday, datetime(2025, 1, 3, 20, 30, tzinfo=timezone.utc), "weekend_force_close")
    rows = weekend_exposure_audit([crossed, closed])
    assert rows[0]["crossed_weekend"] is True
    assert rows[0]["weekend_gap_risk_flag"] is True
    assert rows[1]["did_force_close"] is True
    assert rows[1]["crossed_weekend"] is False
    assert rows[1]["weekend_gap_risk_flag"] is False
