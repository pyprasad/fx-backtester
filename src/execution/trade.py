from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Trade:
    trade_id: str
    signal_id: str
    symbol: str
    direction: str
    entry_timestamp_utc: datetime
    exit_timestamp_utc: datetime
    entry_price: float
    exit_price: float
    initial_stop: float
    final_stop: float
    target_price: float
    size: float
    risk_amount: float
    gross_pnl: float
    net_pnl: float
    pnl_r: float
    max_favourable_excursion: float
    max_adverse_excursion: float
    duration_seconds: float
    duration_hours: float
    duration_days: float
    exit_reason: str
    spread_pips_at_entry: float
    spread_pips_at_exit: float
    partial_exits: list[dict] = field(default_factory=list)
    status: str = "CLOSED"
    session: str = ""
