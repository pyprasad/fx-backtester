import numpy as np
import polars as pl


class EquitySimulator:
    def __init__(self, starting_balance: float, risk_per_trade_percent: float, ruin_percent=50):
        self.starting_balance = starting_balance
        self.risk_fraction = risk_per_trade_percent / 100
        self.ruin_balance = starting_balance * ruin_percent / 100

    def simulate(self, trades: pl.DataFrame, mode="r_compounding") -> dict:
        rs = trades["pnl_r"].cast(pl.Float64).to_numpy()
        pnls, equity = [], [self.starting_balance]
        for index, value in enumerate(rs):
            pnl = (
                equity[-1] * self.risk_fraction * value
                if mode == "r_compounding" else float(trades["net_pnl"][index])
            )
            pnls.append(pnl)
            equity.append(equity[-1] + pnl)
        curve = np.asarray(equity)
        peaks = np.maximum.accumulate(curve)
        drawdowns = np.divide(peaks - curve, peaks, out=np.zeros_like(curve), where=peaks != 0) * 100
        pnl_values = np.asarray(pnls)
        wins, losses = pnl_values[pnl_values > 0], pnl_values[pnl_values <= 0]

        def longest(positive):
            best = current = 0
            for value in rs:
                current = current + 1 if (value > 0) == positive else 0
                best = max(best, current)
            return best

        return {
            "ending_balance": round(float(curve[-1]), 4),
            "total_return_percent": round(float((curve[-1] / self.starting_balance - 1) * 100), 4),
            "max_drawdown_percent": round(float(drawdowns.max()), 4),
            "max_drawdown_amount": round(float((peaks - curve).max()), 4),
            "profit_factor": round(float(wins.sum() / abs(losses.sum())) if losses.sum() else 0, 4),
            "win_rate": round(float((rs > 0).mean() * 100) if len(rs) else 0, 4),
            "average_r": round(float(rs.mean()) if len(rs) else 0, 4),
            "worst_trade_r": round(float(rs.min()) if len(rs) else 0, 4),
            "best_trade_r": round(float(rs.max()) if len(rs) else 0, 4),
            "consecutive_losses_max": longest(False), "consecutive_wins_max": longest(True),
            "min_equity": round(float(curve.min()), 4), "equity_curve": curve.tolist(),
            "ruin_flag": bool(curve.min() < self.ruin_balance), "loss_flag": bool(curve[-1] < self.starting_balance),
            "drawdown_above_10_flag": bool(drawdowns.max() > 10),
            "drawdown_above_15_flag": bool(drawdowns.max() > 15),
        }
