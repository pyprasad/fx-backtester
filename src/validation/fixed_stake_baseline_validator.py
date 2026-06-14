import hashlib
import json
from pathlib import Path


def validate_fixed_stake_baseline(config, trades: list, metrics: dict, audit_rows: list[dict]) -> dict:
    errors = []
    sizing, weekend = config.position_sizing, config.weekend_policy
    force = weekend.get("force_close_on_friday", {})
    selected = config.broker_guardrails.get(
        "selected_guardrail_candidate",
        config.broker_execution_guardrails.get("selected_guardrail_candidate"),
    )
    minimum = config.broker_guardrails.get(
        "min_initial_risk_pips",
        config.broker_execution_guardrails.get("minimum_initial_risk", {}).get(
            "default_min_initial_risk_pips"
        ),
    )

    _expect(errors, sizing.get("mode") == "fixed_spread_bet_stake", "POSITION_SIZING_MODE_INVALID")
    _expect(errors, float(sizing.get("stake_per_pip_gbp", 0)) == 0.04, "STAKE_PER_PIP_NOT_004")
    _expect(errors, weekend.get("policy_name") == "force_close_friday_20_30", "WEEKEND_POLICY_INVALID")
    _expect(errors, weekend.get("enabled") is True, "WEEKEND_POLICY_DISABLED")
    _expect(errors, force.get("enabled") is True, "FRIDAY_FORCE_CLOSE_DISABLED")
    _expect(errors, force.get("close_time_utc") == "20:30", "FRIDAY_FORCE_CLOSE_TIME_INVALID")
    _expect(errors, selected == "min_risk_3pips", "SELECTED_GUARDRAIL_INVALID")
    _expect(errors, float(minimum or 0) == 3.0, "MIN_INITIAL_RISK_INVALID")
    _expect(errors, not any(row["crossed_weekend"] for row in audit_rows), "WEEKEND_CROSSING_TRADE")
    _expect(errors, not any(row["weekend_gap_risk_flag"] for row in audit_rows), "WEEKEND_GAP_RISK_TRADE")
    _expect(errors, float(metrics.get("worst_trade_r", 0)) > -3.0, "WORST_TRADE_BELOW_MINUS_3R")
    old_gap = any(
        row["crossed_weekend"]
        and (abs(float(row["pnl_r"]) + 14.7708) < 0.1 or abs(float(row["pnl_pips"]) + 205.1) < 1)
        for row in audit_rows
    )
    _expect(errors, not old_gap, "OLD_WEEKEND_GAP_LOSS_PRESENT")
    stake = float(sizing.get("stake_per_pip_gbp", 0))
    _expect(
        errors,
        abs(float(metrics.get("net_profit_gbp", 0)) - float(metrics.get("total_pips", 0)) * stake) < 0.011,
        "FIXED_STAKE_PNL_MISMATCH",
    )
    _expect(
        errors,
        abs(
            float(metrics.get("ending_balance", 0))
            - float(metrics.get("starting_balance", 0))
            - float(metrics.get("net_profit_gbp", 0))
        ) < 0.011,
        "ENDING_BALANCE_MISMATCH",
    )
    config_path = str(config.config_path or "")
    effective = config.model_dump(exclude={"base_dir", "config_path"})
    config_hash = hashlib.sha256(
        json.dumps(effective, default=str, sort_keys=True).encode()
    ).hexdigest()
    return {
        "config_path": config_path,
        "config_hash": config_hash,
        "validation_status": "PASS" if not errors else "FAILED_VALIDATION",
        "validation_errors": "|".join(errors),
        "weekend_policy_enabled": bool(weekend.get("enabled")),
        "weekend_policy_name": weekend.get("policy_name", ""),
        "friday_force_close_enabled": bool(force.get("enabled")),
        "friday_force_close_time_utc": force.get("close_time_utc", ""),
        "selected_guardrail_candidate": selected or "",
        "min_initial_risk_pips": float(minimum or 0),
        "weekend_crossing_trade_count": sum(row["crossed_weekend"] for row in audit_rows),
        "weekend_gap_risk_trade_count": sum(row["weekend_gap_risk_flag"] for row in audit_rows),
        "old_weekend_gap_removed": not old_gap,
        "data_period_start": config.data.get("period_start", ""),
        "data_period_end": config.data.get("period_end", ""),
    }


def write_validation_report(path: str | Path, validation: dict) -> None:
    Path(path).write_text(json.dumps(validation, indent=2))


def _expect(errors: list[str], condition: bool, reason: str) -> None:
    if not condition:
        errors.append(reason)
