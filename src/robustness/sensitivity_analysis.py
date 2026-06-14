from statistics import median


def sensitivity_level(baseline: dict, variant: dict) -> str:
    if not variant["pass_flag"]:
        return "CLIFF"
    baseline_return = abs(float(baseline["total_return_percent"]))
    relative_delta = (
        (variant["total_return_percent"] - baseline["total_return_percent"]) / baseline_return * 100
        if baseline_return else 0
    )
    if variant["profit_factor"] < 1.4:
        return "HIGH"
    return "LOW" if abs(relative_delta) <= 25 else "MEDIUM"


def one_factor_sensitivity(rows: list[dict]) -> list[dict]:
    baseline = next(row for row in rows if row["variant_name"] == "baseline_original")
    output = []
    for row in rows:
        if row["test_type"] != "one_factor_at_a_time" or row["run_status"] != "SUCCESS":
            continue
        overrides = __import__("json").loads(row["parameter_overrides_json"])
        parameter, tested = next(iter(overrides.items()))
        result = {
            "parameter_name": parameter, "baseline_value": __import__("json").loads(
                baseline["parameter_overrides_json"]
            ).get(parameter), "tested_value": tested, "variant_name": row["variant_name"],
        }
        for name, label in (
            ("total_return_percent", "return"), ("profit_factor", "profit_factor"),
            ("average_r", "average_r"), ("max_drawdown_percent", "drawdown"),
            ("worst_trade_r", "worst_trade"),
        ):
            result[f"baseline_{label}"] = baseline[name]
            result[f"variant_{label}"] = row[name]
            result[f"{label}_delta"] = round(row[name] - baseline[name], 4)
        result["trade_count_delta"] = row["total_trades"] - baseline["total_trades"]
        result["pass_flag"] = row["pass_flag"]
        result["sensitivity_level"] = sensitivity_level(baseline, row)
        output.append(result)
    return output


def paired_summary(pair_name: str, rows: list[dict]) -> dict:
    successful = [row for row in rows if row["run_status"] == "SUCCESS"]
    passes = sum(row["pass_flag"] for row in successful)
    percent = passes / len(rows) * 100 if rows else 0
    cliffs = len(rows) - passes
    verdict = "STRONG" if percent >= 75 and cliffs == 0 else "PASS" if percent >= 60 and cliffs <= 1 else "WARNING" if percent >= 50 else "FAIL"
    def med(key):
        return round(median(row[key] for row in successful), 4) if successful else 0

    return {
        "pair_name": pair_name, "total_variants": len(rows), "pass_variants": passes,
        "pass_percent": round(percent, 4), "median_return_percent": med("total_return_percent"),
        "median_profit_factor": med("profit_factor"), "median_average_r": med("average_r"),
        "median_drawdown": med("max_drawdown_percent"),
        "worst_trade_min": min((row["worst_trade_r"] for row in successful), default=0),
        "cliff_count": cliffs, "verdict": verdict,
    }


def local_neighbourhood_analysis(rows: list[dict]) -> tuple[list[dict], dict]:
    local = [row for row in rows if row["test_type"] == "local_neighbourhood" or row["variant_name"] == "baseline_original"]
    wanted = {"baseline_minus_small", "baseline_original", "baseline_plus_small"}
    local = [row for row in local if row["variant_name"] in wanted]
    by_name = {row["variant_name"]: row for row in local}
    baseline_passes = by_name.get("baseline_original", {}).get("pass_flag", False)
    isolated = baseline_passes and not by_name.get("baseline_minus_small", {}).get("pass_flag", False) and not by_name.get("baseline_plus_small", {}).get("pass_flag", False)
    details = [
        {key: row.get(key) for key in ("variant_name", "total_return_percent", "profit_factor",
          "max_drawdown_percent", "average_r", "worst_trade_r", "pass_flag")}
        | {"verdict": "PASS" if row.get("pass_flag") else "FAIL"}
        for row in local
    ]
    passed = sum(row.get("pass_flag", False) for row in local)
    return details, {
        "neighbourhood_variant_count": len(local), "neighbourhood_pass_count": passed,
        "neighbourhood_pass_percent": round(passed / len(local) * 100, 4) if local else 0,
        "baseline_isolated_flag": isolated,
    }
