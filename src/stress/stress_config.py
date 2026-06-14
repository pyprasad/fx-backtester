REQUIRED_TRADE_COLUMNS = {
    "pnl_r", "net_pnl", "direction", "exit_reason", "duration_days",
    "spread_pips_at_entry", "spread_pips_at_exit", "initial_risk_pips",
}


def validate_trade_columns(columns: list[str]) -> None:
    missing = REQUIRED_TRADE_COLUMNS - set(columns)
    if missing:
        raise ValueError(f"Stress trade log is missing required columns: {', '.join(sorted(missing))}")
