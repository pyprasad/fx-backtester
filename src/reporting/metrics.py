from statistics import mean, median

from src.execution.trade import Trade


def _round_metrics(metrics: dict) -> dict:
    money = {
        "starting_balance", "ending_balance", "gross_profit", "gross_loss", "net_profit",
        "max_drawdown_amount",
    }
    spreads = {"average_spread_pips_at_entry", "average_spread_pips_at_exit"}
    return {
        key: (
            round(value, 2) if key in money
            else round(value, 3) if key in spreads
            else round(value, 4) if isinstance(value, float)
            else value
        )
        for key, value in metrics.items()
    }


def calculate_metrics(trades: list[Trade], starting_balance: float) -> dict:
    pnl = [t.net_pnl for t in trades]
    rs = [t.pnl_r for t in trades]
    wins, losses = [x for x in pnl if x > 0], [x for x in pnl if x <= 0]
    ending = starting_balance + sum(pnl)
    equity, peak, max_dd = starting_balance, starting_balance, 0.0
    for value in pnl:
        equity += value
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    def longest(predicate):
        best = current = 0
        for trade in trades:
            current = current + 1 if predicate(trade) else 0
            best = max(best, current)
        return best

    short = [t for t in trades if t.direction == "SHORT"]
    long = [t for t in trades if t.direction == "LONG"]
    months = len({t.exit_timestamp_utc.strftime("%Y-%m") for t in trades})
    return _round_metrics({
        "starting_balance": starting_balance, "ending_balance": ending,
        "total_return_percent": (ending / starting_balance - 1) * 100,
        "total_trades": len(trades), "winning_trades": len(wins), "losing_trades": len(losses),
        "win_rate": len(wins) / len(trades) * 100 if trades else 0,
        "gross_profit": sum(wins), "gross_loss": sum(losses), "net_profit": sum(pnl),
        "profit_factor": sum(wins) / abs(sum(losses)) if losses else 0,
        "max_drawdown_percent": max_dd / peak * 100 if peak else 0, "max_drawdown_amount": max_dd,
        "average_r": mean(rs) if rs else 0, "expectancy_r": mean(rs) if rs else 0,
        "average_win_r": mean([r for r in rs if r > 0]) if wins else 0,
        "average_loss_r": mean([r for r in rs if r <= 0]) if losses else 0,
        "best_trade_r": max(rs, default=0), "worst_trade_r": min(rs, default=0),
        "average_trade_duration": mean([t.duration_hours for t in trades]) if trades else 0,
        "median_trade_duration": median([t.duration_hours for t in trades]) if trades else 0,
        "trades_per_month": len(trades) / months if months else 0,
        "consecutive_losses_max": longest(lambda t: t.net_pnl <= 0),
        "consecutive_wins_max": longest(lambda t: t.net_pnl > 0),
        "short_trade_count": len(short), "short_win_rate": sum(t.net_pnl > 0 for t in short) / len(short) * 100 if short else 0,
        "long_trade_count": len(long), "long_win_rate": sum(t.net_pnl > 0 for t in long) / len(long) * 100 if long else 0,
        "average_spread_pips_at_entry": mean([t.spread_pips_at_entry for t in trades]) if trades else 0,
        "average_spread_pips_at_exit": mean([t.spread_pips_at_exit for t in trades]) if trades else 0,
        "stop_loss_exit_count": sum(t.exit_reason == "stop_loss" for t in trades),
        "take_profit_exit_count": sum(t.exit_reason == "take_profit" for t in trades),
        "trailing_stop_exit_count": sum(t.exit_reason == "trailing_stop" for t in trades),
        "max_duration_exit_count": sum(t.exit_reason == "max_duration" for t in trades),
    })
