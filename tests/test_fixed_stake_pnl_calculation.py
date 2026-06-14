import pytest

from src.risk.position_sizer import pnl_pips


def test_short_profit_and_loss_pips_convert_to_fixed_gbp():
    assert pnl_pips(160.20, 160.00, "SHORT", 0.01) == pytest.approx(20)
    assert pnl_pips(160.20, 160.00, "SHORT", 0.01) * 0.04 == pytest.approx(0.80)
    assert pnl_pips(160.20, 160.30, "SHORT", 0.01) == pytest.approx(-10)
    assert pnl_pips(160.20, 160.30, "SHORT", 0.01) * 0.04 == pytest.approx(-0.40)


def test_long_profit_pips_convert_to_fixed_gbp():
    assert pnl_pips(160.20, 160.30, "LONG", 0.01) == pytest.approx(10)
    assert pnl_pips(160.20, 160.30, "LONG", 0.01) * 0.04 == pytest.approx(0.40)
