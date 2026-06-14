import csv
import html
import json
from pathlib import Path


def _rows(path: Path) -> list[dict]:
    with path.open() as handle:
        return list(csv.DictReader(handle))


def _one(path: Path) -> dict:
    return _rows(path)[0]


def write_fixed_stake_comparison(
    baseline_run: str | Path, fixed_run: str | Path, output_stem: str | Path
) -> dict:
    baseline_run, fixed_run, output_stem = Path(baseline_run), Path(fixed_run), Path(output_stem)
    baseline, fixed = _rows(baseline_run / "trade_log.csv"), _rows(fixed_run / "trade_log.csv")
    baseline_summary, fixed_summary = (
        _one(baseline_run / "strategy_summary.csv"), _one(fixed_run / "strategy_summary.csv")
    )
    paired = min(len(baseline), len(fixed))
    entry_matches = sum(
        baseline[i]["entry_timestamp_utc"] == fixed[i]["entry_timestamp_utc"] for i in range(paired)
    )
    exit_matches = sum(
        baseline[i]["exit_timestamp_utc"] == fixed[i]["exit_timestamp_utc"] for i in range(paired)
    )
    reason_matches = sum(baseline[i]["exit_reason"] == fixed[i]["exit_reason"] for i in range(paired))
    pips_matches = sum(
        abs(_baseline_pips(baseline[i]) - float(fixed[i]["pnl_pips"])) < 1e-6
        for i in range(paired)
    )
    planned = [float(row["planned_loss_gbp"]) for row in fixed]
    result = {
        "baseline_run": str(baseline_run),
        "fixed_stake_run": str(fixed_run),
        "baseline_trade_count": len(baseline),
        "fixed_stake_trade_count": len(fixed),
        "trade_count_matches": len(baseline) == len(fixed),
        "entry_timestamp_matches": entry_matches,
        "exit_timestamp_matches": exit_matches,
        "exit_reason_matches": reason_matches,
        "pnl_pips_matches": pips_matches,
        "strategy_logic_matches": (
            len(baseline) == len(fixed) == entry_matches == exit_matches == reason_matches == pips_matches
        ),
        "baseline_return_percent": float(baseline_summary["total_return_percent"]),
        "fixed_stake_return_percent": float(fixed_summary["total_return_percent"]),
        "fixed_stake_net_profit_gbp": float(fixed_summary["net_profit_gbp"]),
        "fixed_stake_total_pips": float(fixed_summary["total_pips"]),
        "fixed_stake_max_drawdown_gbp": float(fixed_summary["max_drawdown_gbp"]),
        "planned_loss_gbp_min": min(planned, default=0),
        "planned_loss_gbp_average": sum(planned) / len(planned) if planned else 0,
        "planned_loss_gbp_max": max(planned, default=0),
        "trade_count_difference_explanation": (
            "" if len(baseline) == len(fixed)
            else "Trade counts differ; verify both runs use identical data, strategy, and guardrails."
        ),
    }
    output_stem.parent.mkdir(parents=True, exist_ok=True)
    _write_csv(output_stem.with_suffix(".csv"), result)
    output_stem.with_suffix(".json").write_text(json.dumps(result, indent=2))
    cards = "".join(
        f"<tr><th>{html.escape(key)}</th><td>{html.escape(str(value))}</td></tr>"
        for key, value in result.items()
    )
    output_stem.with_suffix(".html").write_text(
        f"<html><body><h1>Final Baseline vs Fixed £0.04 Stake</h1><table>{cards}</table>"
        "<p>The fixed-stake run must preserve trade timing, exits, and pip outcomes.</p></body></html>"
    )
    return result


def _baseline_pips(row: dict) -> float:
    return float(row["net_pnl"]) / float(row["size"]) / 0.01


def _write_csv(path: Path, row: dict) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)
