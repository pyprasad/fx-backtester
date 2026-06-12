def equity_curve(trades, starting_balance):
    balance = starting_balance
    result = []
    for trade in trades:
        balance += trade.net_pnl
        result.append((trade.exit_timestamp_utc, balance))
    return result
