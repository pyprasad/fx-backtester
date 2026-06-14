from statistics import mean


def funding_summary(adjusted: list[dict], metrics: dict, starting_balance: float) -> dict:
    after_pnl = [row["net_pnl_after_funding"] for row in adjusted]
    after_r = [row["pnl_r_after_funding"] for row in adjusted]
    wins, losses = [x for x in after_pnl if x > 0], [x for x in after_pnl if x <= 0]
    return {
        "total_trades": len(adjusted),
        "trades_held_overnight": sum(row["overnight_funding_event_count"] > 0 for row in adjusted),
        "total_funding_events": sum(row["overnight_funding_event_count"] for row in adjusted),
        "total_funding_days": sum(row["funding_days"] for row in adjusted),
        "wednesday_triple_rollover_events": sum(row["wednesday_triple_rollover_count"] for row in adjusted),
        "estimated_total_funding_pips": round(sum(row["estimated_funding_pips"] for row in adjusted), 4),
        "estimated_total_funding_r": round(sum(row["estimated_funding_r"] for row in adjusted), 4),
        "average_funding_r_per_trade": round(mean([row["estimated_funding_r"] for row in adjusted]), 4) if adjusted else 0,
        "max_funding_r_single_trade": round(max((row["estimated_funding_r"] for row in adjusted), default=0), 4),
        "return_before_funding": metrics["total_return_percent"],
        "return_after_funding": round(sum(after_pnl) / starting_balance * 100, 4),
        "profit_factor_before_funding": metrics["profit_factor"],
        "profit_factor_after_funding": round(sum(wins) / abs(sum(losses)), 4) if losses else 0,
        "average_r_before_funding": metrics["average_r"],
        "average_r_after_funding": round(mean(after_r), 4) if after_r else 0,
        "worst_trade_r_after_funding": round(min(after_r, default=0), 4),
    }


def score_guardrail(row: dict, settings: dict) -> tuple[int, str]:
    total_signals = row["accepted_signals"] + row["rejected_signals"]
    deductions = (
        20 if row["return_percent_after_funding"] <= 0 else 0,
        15 if row["profit_factor_after_funding"] < 1.3 else 0,
        15 if row["worst_trade_r_after_funding"] < -2.5 else 0,
        15 if row["max_drawdown_percent"] > 10 else 0,
        10 if row["max_spread_to_risk_ratio"] > .30 else 0,
        10 if row["accepted_below_broker_minimum"] else 0,
        10 if settings.get("minimum_initial_risk", {}).get("enabled") and row["accepted_below_configured_minimum"] else 0,
        10 if settings.get("spread_to_risk_filter", {}).get("enabled") and row["accepted_above_configured_ratio"] else 0,
        5 if row["return_percent_before_funding"] > 0 and row["return_percent_after_funding"] < row["return_percent_before_funding"] * .8 else 0,
        5 if row["wednesday_triple_rollover_count"] > row["total_trades"] * .25 else 0,
        5 if total_signals and row["rejected_signals"] / total_signals > .5 else 0,
    )
    additions = (
        5 if row["worst_trade_r_after_funding"] >= -2.5 else 0,
        5 if row["profit_factor_after_funding"] >= 1.5 else 0,
        5 if row["max_drawdown_percent"] < 5 else 0,
        5 if not row["accepted_below_broker_minimum"] and (
            not settings.get("minimum_initial_risk", {}).get("enabled") or not row["accepted_below_configured_minimum"]
        ) and (not settings.get("spread_to_risk_filter", {}).get("enabled") or not row["accepted_above_configured_ratio"]) else 0,
    )
    score = max(0, min(100, 100 - sum(deductions) + sum(additions)))
    verdict = "STRONG_GUARDRAIL" if score >= 85 else "PASS" if score >= 70 else "WARNING" if score >= 50 else "FAIL"
    return score, verdict


def trade_guardrail_stats(trades, settings: dict) -> dict:
    risks = [float(t.initial_risk_pips or 0) for t in trades]
    ratios = [float(t.spread_pips_at_entry) / risk if risk else float("inf") for t, risk in zip(trades, risks)]
    broker_min = float(settings["broker_distance_rules"]["min_stop_distance_pips"])
    configured_min = float(settings["minimum_initial_risk"]["default_min_initial_risk_pips"])
    configured_ratio = float(settings["spread_to_risk_filter"]["default_max_spread_to_initial_risk_ratio"])
    return {
        **{f"trades_below_{value}_pips_risk": sum(risk < value for risk in risks) for value in (2, 3, 5, 8, 10)},
        "max_spread_to_risk_ratio": round(max(ratios, default=0), 4),
        "average_spread_to_risk_ratio": round(mean(ratios), 4) if ratios else 0,
        **{f"trades_spread_to_risk_above_{value}pct": sum(ratio > value / 100 for ratio in ratios) for value in (10, 20, 30)},
        "accepted_below_broker_minimum": sum(risk < broker_min for risk in risks),
        "accepted_below_configured_minimum": sum(risk < configured_min for risk in risks),
        "accepted_above_configured_ratio": sum(ratio > configured_ratio for ratio in ratios),
    }
