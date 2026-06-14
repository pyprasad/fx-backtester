import csv
import json
from pathlib import Path


def _one(path: Path) -> dict:
    if not path.exists() or not path.read_text().strip():
        return {}
    if path.suffix == ".json":
        return json.loads(path.read_text())
    with path.open() as handle:
        return next(csv.DictReader(handle), {})


def _all(path: Path) -> list[dict]:
    if not path.exists() or not path.read_text().strip():
        return []
    with path.open() as handle:
        return list(csv.DictReader(handle))


def _number(value, default=None):
    if value in (None, ""):
        return default
    return float(value)


def _count_true(rows: list[dict], key: str) -> int:
    return sum(str(row.get(key, "")).lower() == "true" for row in rows)


def collect_candidate_metrics(candidate: dict, backtest: Path, guardrail: dict,
                              stability: Path | None = None, walk_forward: Path | None = None,
                              stress: Path | None = None) -> dict:
    base, funding = _one(backtest / "strategy_summary.csv"), _one(backtest / "funding_summary.csv")
    stability_summary = _one(stability / "stability_summary.csv") if stability else {}
    concentration = _one(stability / "concentration_summary.csv") if stability else {}
    yearly = _all(stability / "yearly_stability.csv") if stability else []
    quarterly = _all(stability / "quarterly_stability.csv") if stability else []
    rolling6 = _all(stability / "rolling_6_month_stability.csv") if stability else []
    rolling12 = _all(stability / "rolling_12_month_stability.csv") if stability else []
    wf = _one(walk_forward / "walk_forward_summary.csv") if walk_forward else {}
    stress_summary = _one(stress / "stress_summary.csv") if stress else {}
    execution = _all(stress / "execution_stress_summary.csv") if stress else []
    missed = _all(stress / "missed_trade_stress_summary.csv") if stress else []
    sequence = _all(stress / "sequence_stress_summary.csv") if stress else []
    missing = [
        name for name, data in (
            ("base_backtest", base), ("funding_adjusted_metrics", funding),
            ("broker_guardrail_metrics", guardrail), ("stability", stability_summary),
            ("walk_forward", wf), ("monte_carlo_stress", stress_summary),
            ("execution_stress", execution),
        ) if not data
    ]

    def scenario(rows, name, key, default=None):
        row = next((item for item in rows if item.get("scenario_name") == name), {})
        return _number(row.get(key), default)

    worst_execution = min((_number(row.get("worst_trade_r"), 0) for row in execution), default=None)
    return {
        "candidate_name": candidate["name"], "guardrail_variant_name": candidate["guardrail_variant_name"],
        "description": candidate["description"], "missing_validation_layers": "|".join(missing),
        "total_trades": _number(base.get("total_trades"), 0), "accepted_signals": _number(guardrail.get("accepted_signals"), 0),
        "rejected_signals": _number(guardrail.get("rejected_signals"), 0),
        "return_before_funding": _number(funding.get("return_before_funding"), _number(base.get("total_return_percent"), 0)),
        "return_after_funding": _number(funding.get("return_after_funding"), 0),
        "profit_factor_before_funding": _number(funding.get("profit_factor_before_funding"), _number(base.get("profit_factor"), 0)),
        "profit_factor_after_funding": _number(funding.get("profit_factor_after_funding"), 0),
        "average_r_before_funding": _number(funding.get("average_r_before_funding"), _number(base.get("average_r"), 0)),
        "average_r_after_funding": _number(funding.get("average_r_after_funding"), 0),
        "max_drawdown_percent": _number(base.get("max_drawdown_percent"), 0),
        "worst_trade_r": _number(base.get("worst_trade_r"), 0), "best_trade_r": _number(base.get("best_trade_r"), 0),
        "win_rate": _number(base.get("win_rate"), 0), "trades_per_month": _number(base.get("trades_per_month"), 0),
        **{key: _number(guardrail.get(key), 0) for key in (
            "trades_below_2_pips_risk", "trades_below_3_pips_risk", "trades_below_5_pips_risk",
            "max_spread_to_risk_ratio", "average_spread_to_risk_ratio", "broker_distance_rejections",
            "min_risk_rejections", "spread_risk_rejections", "funding_time_rejections",
            "overnight_trade_count", "funding_days", "wednesday_triple_rollover_count",
        )},
        "stability_score": _number(stability_summary.get("stability_score")),
        "stability_verdict": stability_summary.get("verdict"),
        "profitable_years": _count_true(yearly, "positive_year_flag"),
        "profitable_quarters": _count_true(quarterly, "positive_quarter_flag"),
        "profitable_active_months_percent": _number(stability_summary.get("positive_months_percent")),
        "profitable_6m_windows_percent": _count_true(rolling6, "positive_window_flag") / len(rolling6) * 100 if rolling6 else None,
        "profitable_12m_windows_percent": _count_true(rolling12, "positive_window_flag") / len(rolling12) * 100 if rolling12 else None,
        "top_3_month_contribution_percent": _number(concentration.get("top_3_month_profit_contribution_percent")),
        "top_10_trade_contribution_percent": _number(concentration.get("top_10_trade_profit_contribution_percent")),
        "walk_forward_score": _number(wf.get("walk_forward_score")), "walk_forward_verdict": wf.get("final_verdict"),
        "anchored_profitable_test_years": _number(wf.get("anchored_positive_test_windows")),
        "rolling_profitable_test_window_percent": _number(wf.get("rolling_positive_test_percent")),
        "average_test_profit_factor": _number(wf.get("average_test_profit_factor")),
        "median_test_profit_factor": _number(wf.get("median_test_profit_factor")),
        "average_test_r": _number(wf.get("average_test_average_r")),
        "worst_test_trade_r": _number(wf.get("worst_test_trade_r")),
        "max_test_drawdown_percent": _number(wf.get("max_test_drawdown_percent")),
        "stress_score": _number(stress_summary.get("stress_score")), "stress_verdict": stress_summary.get("verdict"),
        "bootstrap_p5_return": _number(stress_summary.get("p5_return_percent")),
        "bootstrap_p95_drawdown": _number(stress_summary.get("p95_max_drawdown_percent")),
        "bootstrap_probability_of_loss": _number(stress_summary.get("probability_of_loss_percent")),
        "bootstrap_probability_drawdown_above_10": _number(stress_summary.get("probability_drawdown_above_10_percent")),
        "missed_best_10_return": scenario(missed, "miss_best_trades_10pct", "median_return_percent"),
        "missed_best_20_return": scenario(missed, "miss_best_trades_20pct", "median_return_percent"),
        "worst_trades_first_drawdown": scenario(sequence, "worst_trades_first", "max_drawdown_percent"),
        "execution_stress_failure_count": sum(row.get("verdict") == "FAIL" for row in execution),
        "worst_execution_stress_trade_r": worst_execution,
        "spread_2x_return": scenario(execution, "spread_2.0_both", "total_return_percent"),
        "spread_2x_profit_factor": scenario(execution, "spread_2.0_both", "profit_factor"),
        "slippage_1pip_return": scenario(execution, "slippage_1.0_both", "total_return_percent"),
        "slippage_1pip_profit_factor": scenario(execution, "slippage_1.0_both", "profit_factor"),
        "friday_close_5pip_slippage_return": scenario(execution, "friday_close_5.0_pips", "total_return_percent"),
    }
