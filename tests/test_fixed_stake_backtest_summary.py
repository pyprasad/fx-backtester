from datetime import datetime, timezone

import pytest

from src.execution.trade import Trade
from src.reporting.metrics import calculate_metrics


def _trade(pips):
    pnl = pips * 0.04
    return Trade(
        "t", "s", "USDJPY", "SHORT", datetime.now(timezone.utc), datetime.now(timezone.utc),
        160.2, 160.2 - pips * 0.01, 160.25, 160.25, 160.0, 4, 0.2, pnl, pnl,
        pnl / 0.2, 0, 0, 1, 1 / 3600, 1 / 86400, "take_profit" if pips > 0 else "stop_loss",
        0.5, 0.5, position_sizing_mode="fixed_spread_bet_stake", stake_per_pip_gbp=0.04,
        pnl_pips=pips, pnl_gbp=pnl, planned_loss_gbp=0.2,
    )


def test_fixed_stake_summary_totals_pips_gbp_and_ending_balance():
    metrics = calculate_metrics([_trade(20), _trade(-10)], 10000)
    assert metrics["total_pips"] == pytest.approx(10)
    assert metrics["net_profit_gbp"] == pytest.approx(0.40)
    assert metrics["ending_balance"] == pytest.approx(10000.40)
    assert metrics["estimated_loss_at_5pip_stop_gbp"] == pytest.approx(0.20)
