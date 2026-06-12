from dataclasses import dataclass
from datetime import datetime


@dataclass
class Signal:
    signal_id: str
    timestamp_utc: datetime
    timestamp_london: datetime
    symbol: str
    direction: str
    entry_type: str
    signal_price_mid: float
    trend_timeframe: str
    entry_timeframe: str
    reason_codes: list[str]
    indicator_snapshot: dict[str, float]
    proposed_stop: float
    proposed_target: float
    spread_pips_at_signal: float
    session: str = ""
