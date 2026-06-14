from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class IGSession:
    cst: str
    security_token: str
    account_id: str
    lightstreamer_endpoint: str
    created_at: datetime
    expires_at: datetime | None = None
    raw_account_info: dict[str, Any] = field(default_factory=dict)

    def redacted(self) -> dict:
        return {
            "account_id": redact(self.account_id), "lightstreamer_endpoint": self.lightstreamer_endpoint,
            "created_at": self.created_at.isoformat(), "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "cst": "***", "security_token": "***",
        }


@dataclass
class InternalTick:
    timestamp_utc: datetime
    bid: float
    ask: float
    mid: float
    spread_pips: float
    source: str
    epic: str
    delayed: bool
    bid_vol: float | None = None
    ask_vol: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def row(self) -> dict:
        row = asdict(self)
        row["timestamp_utc"] = self.timestamp_utc.isoformat()
        return row


@dataclass
class DryRunOrder:
    deal_reference: str
    epic: str
    direction: str
    size: float
    order_type: str
    level: float | None
    stop_distance: float | None
    stop_level: float | None
    limit_distance: float | None
    limit_level: float | None
    currency: str
    force_open: bool
    guaranteed_stop: bool
    time_in_force: str
    expiry: str
    dry_run_only: bool = True
    validation_status: str = "NOT_READY"
    validation_errors: list[str] = field(default_factory=list)
    validation_warnings: list[str] = field(default_factory=list)

    def payload(self) -> dict:
        return {
            key: value for key, value in asdict(self).items()
            if key not in {"validation_status", "validation_errors", "validation_warnings"}
        }


def redact(value: str | None, visible: int = 3) -> str:
    if not value:
        return ""
    return f"{value[:visible]}***{value[-visible:]}" if len(value) > visible * 2 else "***"
