import json


FAIL_RULES = (
    ("NEGATIVE_RETURN", lambda row: row["total_return_percent"] <= 0),
    ("LOW_PROFIT_FACTOR", lambda row: row["profit_factor"] < 1.3),
    ("NEGATIVE_AVERAGE_R", lambda row: row["average_r"] <= 0),
    ("HIGH_DRAWDOWN", lambda row: row["max_drawdown_percent"] > 10),
    ("WORST_TRADE_TOO_LARGE", lambda row: row["worst_trade_r"] < -2.5),
    ("TOO_FEW_TRADES", lambda row: row["total_trades"] < 50),
)


def collect_variant_metrics(variant, metrics: dict | None, run_status="SUCCESS", error_message="") -> dict:
    if run_status == "ERROR" or metrics is None:
        return {
            "variant_id": variant.variant_id, "variant_name": variant.variant_name,
            "test_type": variant.test_type, "parameter_overrides_json": json.dumps(variant.parameter_overrides),
            "is_baseline": variant.is_baseline, "run_status": "ERROR", "error_message": error_message,
            "profitable_flag": False, "pass_flag": False, "fail_reason": "BACKTEST_ERROR",
            "safety_flag": False, "score": 0,
        }
    row = {
        "variant_id": variant.variant_id, "variant_name": variant.variant_name,
        "test_type": variant.test_type, "parameter_overrides_json": json.dumps(variant.parameter_overrides, sort_keys=True),
        "is_baseline": variant.is_baseline, "run_status": run_status, "error_message": error_message,
        **metrics,
    }
    row["average_trade_duration_days"] = metrics.get("average_trade_duration", 0) / 24
    row["median_trade_duration_days"] = metrics.get("median_trade_duration", 0) / 24
    reasons = [name for name, failed in FAIL_RULES if failed(row)]
    row["profitable_flag"] = row["total_return_percent"] > 0
    row["pass_flag"] = not reasons
    row["fail_reason"] = "|".join(reasons)
    row["safety_flag"] = row["max_drawdown_percent"] <= 10 and row["worst_trade_r"] >= -2.5
    row["score"] = round(
        max(0, row["total_return_percent"] + row["profit_factor"] * 10 + row["average_r"] * 10
            - row["max_drawdown_percent"] * 2), 4
    )
    return row
