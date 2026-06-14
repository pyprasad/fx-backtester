from datetime import datetime, time, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo


def funding_cutoffs(entry_utc: datetime, exit_utc: datetime, settings: dict) -> list[datetime]:
    zone = ZoneInfo(settings["timezone"])
    cutoff = time.fromisoformat(settings["cutoff_time"])
    current = entry_utc.astimezone(zone).date()
    end = exit_utc.astimezone(zone).date()
    result = []
    while current <= end:
        local = datetime.combine(current, cutoff, zone)
        utc = local.astimezone(timezone.utc)
        if entry_utc < utc < exit_utc:
            result.append(local)
        current += timedelta(days=1)
    return result


def calculate_trade_funding(trade, settings: dict, daily_funding_pips: float) -> tuple[dict, list[dict]]:
    cutoffs = funding_cutoffs(trade.entry_timestamp_utc, trade.exit_timestamp_utc, settings)
    events, days = [], 0
    for local in cutoffs:
        funding_days = 3 if settings.get("apply_wednesday_triple_rollover") and local.weekday() == 2 else 1
        days += funding_days
        pips = daily_funding_pips * funding_days
        funding_r = pips / trade.initial_risk_pips if trade.initial_risk_pips else 0
        events.append({
            "event_id": str(uuid4()), "trade_id": trade.trade_id, "timestamp_uk": local,
            "timestamp_utc": local.astimezone(timezone.utc), "weekday": local.strftime("%A"),
            "funding_days": funding_days, "daily_funding_pips": daily_funding_pips,
            "estimated_funding_pips": pips, "estimated_funding_r": funding_r,
            "notes": "Friday funding exposure" if local.weekday() == 4 else "",
        })
    total_pips = days * daily_funding_pips
    total_r = round(total_pips / trade.initial_risk_pips, 8) if trade.initial_risk_pips else 0
    return {
        "trade_id": trade.trade_id, "overnight_funding_event_count": len(cutoffs),
        "funding_days": days, "wednesday_triple_rollover_count": sum(x.weekday() == 2 for x in cutoffs),
        "estimated_funding_pips": total_pips, "estimated_funding_r": total_r,
        "pnl_r_before_funding": trade.pnl_r, "pnl_r_after_funding": trade.pnl_r - total_r,
        "net_pnl_before_funding": trade.net_pnl,
        "estimated_funding_amount": trade.risk_amount * total_r,
        "net_pnl_after_funding": trade.net_pnl - trade.risk_amount * total_r,
    }, events
