import pytest

from src.risk.position_sizer import fixed_stake_position_size


def test_fixed_stake_position_size_and_planned_loss():
    size, planned_loss = fixed_stake_position_size(0.04, 0.01, 160.20, 160.25)
    assert size == 4
    assert planned_loss == pytest.approx(0.20)


def test_fixed_stake_rejects_invalid_values():
    with pytest.raises(ValueError):
        fixed_stake_position_size(0, 0.01, 160.20, 160.25)
