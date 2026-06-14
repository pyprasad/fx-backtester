from datetime import time
from zoneinfo import ZoneInfo

from .broker_rules import GuardrailDecision


def validate_entry_time(timestamp_utc, settings: dict,
                        decision: GuardrailDecision | None = None) -> GuardrailDecision:
    decision = decision or GuardrailDecision()
    guard = settings["entry_time_guard"]
    local = timestamp_utc.astimezone(ZoneInfo(guard["timezone"]))
    decision.timestamp_utc, decision.timestamp_local = timestamp_utc, local
    # The configured cutoff is inclusive: signals at 21:30 UK time are blocked.
    if guard.get("enabled") and local.time() >= time.fromisoformat(guard["block_new_entries_after"]):
        decision.reject("REJECT_AFTER_FUNDING_ENTRY_CUTOFF")
    return decision
