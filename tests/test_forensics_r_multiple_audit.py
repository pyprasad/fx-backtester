from src.forensics.r_multiple_audit import audit_r_multiple, weighted_partial_r


def _trade(pnl_r):
    return {
        "trade_id": "t", "direction": "SHORT", "entry_price": 150.0, "initial_stop": 150.1,
        "exit_price": 149.8, "risk_amount": 25.0, "net_pnl": pnl_r * 25, "pnl_r": pnl_r,
    }


def test_r_multiple_and_large_loss_levels():
    assert audit_r_multiple(_trade(2.0))["price_only_pnl_r"] == 2.0
    assert audit_r_multiple(_trade(-3.0))["loss_threshold_status"] == "WARNING"
    assert audit_r_multiple(_trade(-6.0))["loss_threshold_status"] == "FAIL"


def test_partial_exit_weighted_r():
    result = weighted_partial_r(
        150.0, "SHORT", 0.1,
        [{"price": 149.8, "fraction": 0.5}], 149.6, remaining=1.0,
    )
    assert round(result, 6) == 3.0
