from dataclasses import dataclass, field


@dataclass
class RiskManager:
    starting_balance: float
    max_open_trades_total: int = 1
    max_open_trades_per_market: int = 1
    max_daily_loss_percent: float = 1.0
    max_weekly_loss_percent: float = 3.0
    max_drawdown_percent: float = 10.0
    open_symbols: set[str] = field(default_factory=set)
    daily_pnl: float = 0
    weekly_pnl: float = 0
    peak_balance: float = 0
    current_day: object = None
    current_week: object = None

    def __post_init__(self):
        self.peak_balance = self.starting_balance

    def can_open(self, symbol: str, balance: float) -> tuple[bool, str]:
        if len(self.open_symbols) >= self.max_open_trades_total or symbol in self.open_symbols:
            return False, "max_open_trades"
        if self.daily_pnl <= -self.starting_balance * self.max_daily_loss_percent / 100:
            return False, "daily_loss_limit"
        if self.weekly_pnl <= -self.starting_balance * self.max_weekly_loss_percent / 100:
            return False, "weekly_loss_limit"
        if self.peak_balance and (self.peak_balance - balance) / self.peak_balance * 100 >= self.max_drawdown_percent:
            return False, "drawdown_limit"
        return True, ""

    def roll_periods(self, timestamp) -> None:
        day, week = timestamp.date(), timestamp.isocalendar()[:2]
        if day != self.current_day:
            self.daily_pnl, self.current_day = 0, day
        if week != self.current_week:
            self.weekly_pnl, self.current_week = 0, week

    def record(self, pnl: float, balance: float, timestamp=None) -> None:
        if timestamp:
            self.roll_periods(timestamp)
        self.daily_pnl += pnl
        self.weekly_pnl += pnl
        self.peak_balance = max(self.peak_balance, balance)
