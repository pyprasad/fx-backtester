from src.risk.risk_manager import RiskManager


def test_risk_manager_enforces_open_trade_and_daily_limit():
    manager = RiskManager(10000)
    manager.open_symbols.add("USDJPY")
    assert manager.can_open("USDJPY", 10000)[0] is False
    manager.open_symbols.clear()
    manager.daily_pnl = -101
    assert manager.can_open("USDJPY", 9899)[1] == "daily_loss_limit"
