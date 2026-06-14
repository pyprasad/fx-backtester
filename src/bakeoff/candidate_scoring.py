SIMPLICITY = {"ig_min_stop_only": 100, "min_risk_3pips": 85, "recommended_research_guardrail": 70}


def _clamp(value):
    return round(max(0, min(100, value)), 4)


def hard_fail_reasons(row: dict, rules: dict) -> list[str]:
    checks = [
        (row["worst_trade_r"] < rules["max_worst_trade_r"], "worst_trade_r"),
        (row["max_drawdown_percent"] > rules["max_drawdown_percent"], "max_drawdown_percent"),
        (row["profit_factor_after_funding"] < rules["min_profit_factor_after_funding"], "profit_factor_after_funding"),
        (row["return_after_funding"] <= rules["min_return_after_funding"], "return_after_funding"),
        (row.get("bootstrap_probability_of_loss") is not None and row["bootstrap_probability_of_loss"] > rules["max_monte_carlo_probability_of_loss_percent"], "bootstrap_probability_of_loss"),
        (row.get("bootstrap_probability_drawdown_above_10") is not None and row["bootstrap_probability_drawdown_above_10"] > rules["max_monte_carlo_probability_drawdown_above_10_percent"], "bootstrap_probability_drawdown_above_10"),
        (row.get("worst_execution_stress_trade_r") is not None and row["worst_execution_stress_trade_r"] < rules["max_execution_stress_tail_trade_r"], "worst_execution_stress_trade_r"),
    ]
    return [name for failed, name in checks if failed]


def score_candidates(rows: list[dict], config: dict) -> tuple[list[dict], list[dict]]:
    weights, rules = config["ranking_weights"], config["hard_fail_rules"]
    best_return = max(row["return_after_funding"] for row in rows) or 1
    baseline_trades = max(row.get("baseline_total_trades", row["total_trades"]) for row in rows) or 1
    baseline_return = max(
        row.get("baseline_return_after_funding", row["return_after_funding"]) for row in rows
    ) or 1
    weight_total = sum(weights.values())
    breakdowns = []
    for row in rows:
        missing_stress = any(name in row["missing_validation_layers"] for name in ("monte_carlo_stress", "execution_stress"))
        components = {
            "return_score": _clamp(row["return_after_funding"] / best_return * 100),
            "profit_factor_score": _clamp(row["profit_factor_after_funding"] / 2.5 * 100),
            "average_r_score": _clamp(row["average_r_after_funding"] / .6 * 100),
            "drawdown_score": 100 if row["max_drawdown_percent"] <= 2 else _clamp((10 - row["max_drawdown_percent"]) / 8 * 100),
            "worst_trade_score": 100 if row["worst_trade_r"] >= -2 else _clamp((row["worst_trade_r"] + 2.5) / .5 * 100),
            "monte_carlo_return_score": 0 if row.get("bootstrap_p5_return") is None else (100 if row["bootstrap_p5_return"] > 30 else _clamp(row["bootstrap_p5_return"] / 30 * 100)),
            "monte_carlo_drawdown_score": 0 if row.get("bootstrap_p95_drawdown") is None else (100 if row["bootstrap_p95_drawdown"] < 5 else _clamp((15 - row["bootstrap_p95_drawdown"]) / 10 * 100)),
            "execution_stress_score": 0 if missing_stress else _clamp(100 - row["execution_stress_failure_count"] * 20),
            "trade_retention_score": 100 if row["total_trades"] / baseline_trades >= .9 else 50 if row["total_trades"] / baseline_trades >= .75 else 20,
            "simplicity_score": SIMPLICITY[row["candidate_name"]],
        }
        weighted = sum(components[key] * weights[weight] for key, weight in (
            ("return_score", "return_after_funding"), ("profit_factor_score", "profit_factor_after_funding"),
            ("average_r_score", "average_r_after_funding"), ("drawdown_score", "max_drawdown"),
            ("worst_trade_score", "worst_trade_r"), ("monte_carlo_return_score", "monte_carlo_p5_return"),
            ("monte_carlo_drawdown_score", "monte_carlo_p95_drawdown"),
            ("execution_stress_score", "execution_stress_pass"), ("trade_retention_score", "trade_count_retention"),
            ("simplicity_score", "simplicity"),
        )) / weight_total
        reasons = hard_fail_reasons(row, rules)
        row.update({
            "trade_count_retention_vs_baseline": round(row["total_trades"] / baseline_trades * 100, 4),
            "return_retention_vs_baseline": round(row["return_after_funding"] / baseline_return * 100, 4),
            "safety_improvement_vs_baseline": round(100 - row["max_spread_to_risk_ratio"] * 100, 4),
            "simplicity_score": components["simplicity_score"], "overall_score": round(weighted, 4),
            "hard_fail_flag": bool(reasons), "hard_fail_reasons": "|".join(reasons),
        })
        breakdowns.append({"candidate_name": row["candidate_name"], **components, "weighted_total_score": round(weighted, 4)})
    return rows, breakdowns


def rank_candidates(rows: list[dict], config: dict) -> list[dict]:
    threshold = config["candidate_selection_rules"]["score_close_threshold_points"]
    eligible = [row for row in rows if not row["hard_fail_flag"]]
    ranked = sorted(eligible, key=lambda row: row["overall_score"], reverse=True)
    if len(ranked) > 1:
        close_count = sum(
            ranked[0]["overall_score"] - row["overall_score"] <= threshold for row in ranked
        )
        ranked[:close_count] = sorted(ranked[:close_count], key=lambda row: (
            row["worst_trade_r"], -row["max_drawdown_percent"],
            row["profit_factor_after_funding"], row["simplicity_score"],
        ), reverse=True)
    ranked += [row for row in rows if row["hard_fail_flag"]]
    for index, row in enumerate(ranked, 1):
        row["rank"] = index
        row["recommendation"] = (
            "REJECT" if row["hard_fail_flag"] else
            "HUMAN_REVIEW" if row["missing_validation_layers"] else
            "SELECT" if index == 1 else "BACKUP"
        )
    return ranked
