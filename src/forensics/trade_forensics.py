from ast import literal_eval
from datetime import timedelta
from pathlib import Path
import re

import polars as pl

from src.config.schemas import StrategyConfig
from src.utils.logging import get_logger, timed_stage

from .execution_audit import audit_execution
from .forensic_report import write_forensic_report, write_rows
from .r_multiple_audit import audit_r_multiple
from .stop_audit import audit_stop_path
from .weekend_gap_audit import audit_weekend_gap

logger = get_logger(__name__)


def _partials(value) -> list[dict]:
    if isinstance(value, list):
        return value
    if not value or value == "[]":
        return []
    try:
        parsed = literal_eval(value)
        return parsed if isinstance(parsed, list) else []
    except (ValueError, SyntaxError):
        return [
            {"price": float(price), "fraction": float(fraction)}
            for price, fraction in re.findall(
                r"'price':\s*([0-9.]+),\s*'fraction':\s*([0-9.]+)", str(value)
            )
        ]


class TradeForensicsEngine:
    def __init__(
        self,
        config: StrategyConfig,
        trade_log: str | Path | pl.DataFrame | list[dict],
        normalised_tick_path: str | Path,
        candle_path: str | Path,
        output_path: str | Path,
    ):
        self.config = config
        self.tick_path = Path(normalised_tick_path)
        self.candle_path = Path(candle_path)
        self.output = Path(output_path) / "forensics"
        self.forensic_config = config.forensics
        if isinstance(trade_log, pl.DataFrame):
            self.trades = trade_log
        elif isinstance(trade_log, list):
            self.trades = pl.DataFrame(trade_log)
        else:
            self.trades = pl.read_csv(trade_log, try_parse_dates=True)
        self.results: list[dict] = []
        self.stop_rows: list[dict] = []
        self.execution_rows: list[dict] = []
        self.r_rows: list[dict] = []
        self.weekend_rows: list[dict] = []
        self.flags: list[dict] = []

    def _ticks(self, trade: dict, extra_minutes: int = 0) -> pl.DataFrame:
        start = trade["entry_timestamp_utc"] - timedelta(minutes=extra_minutes)
        end = trade["exit_timestamp_utc"] + timedelta(minutes=extra_minutes)
        return (
            pl.scan_parquet(self.tick_path)
            .filter((pl.col("timestamp_utc") >= start) & (pl.col("timestamp_utc") <= end))
            .collect(engine="streaming")
        )

    def analyze_single_trade(self, trade_id: str) -> dict:
        trade = self.trades.filter(pl.col("trade_id") == trade_id).row(0, named=True)
        ticks = self._ticks(trade)
        tolerance = self.forensic_config["stop_audit"]["tolerance_price"]
        signal_timestamp = trade.get("signal_timestamp_utc")
        slip = self.config.execution.get("default_slippage_points", 0) if self.config.execution.get("slippage_enabled") else 0
        stop = audit_stop_path(trade, ticks, tolerance)
        execution = audit_execution(trade, ticks, signal_timestamp, tolerance, slip)
        r_audit = audit_r_multiple(trade, _partials(trade.get("partial_exits")))
        weekend = audit_weekend_gap(trade, ticks)
        close_side = "bid" if trade["direction"] == "LONG" else "ask"
        move = (pl.col(close_side) - trade["entry_price"]) * (1 if trade["direction"] == "LONG" else -1)
        excursion = ticks.select(
            move.max().alias("mfe"), move.min().alias("mae"),
            pl.col("spread_pips").max().alias("max_spread"),
            pl.col("spread_pips").mean().alias("avg_spread"),
            pl.col("spread_pips").quantile(0.95).alias("p95_spread"),
        ).row(0, named=True) if ticks.height else {}
        integrity_flags = []
        if trade["pnl_r"] < self.forensic_config["r_multiple_audit"]["max_expected_loss_r_warning"]:
            integrity_flags.append("FLAG_LOSS_BEYOND_EXPECTED_R")
        if stop["did_stop_cross_before_recorded_exit"]:
            integrity_flags.append("FLAG_STOP_CROSSED_BEFORE_EXIT")
        if stop["did_target_cross_before_recorded_exit"] and trade["exit_reason"] != "take_profit":
            integrity_flags.append("FLAG_TARGET_CROSSED_BEFORE_EXIT_BUT_NOT_EXITED")
        if not execution["entry_side_matches"] or not execution["exit_side_matches"]:
            integrity_flags.append("FLAG_WRONG_BID_ASK_SIDE_POSSIBLE")
        if weekend["held_over_weekend"]:
            integrity_flags.append("FLAG_HELD_OVER_WEEKEND")
        if (weekend["price_gap_against_position_pips"] or 0) >= 5:
            integrity_flags.append("FLAG_LARGE_GAP_AGAINST_POSITION")
        if not execution["exit_tick_found"]:
            integrity_flags.append("FLAG_EXIT_PRICE_NOT_AVAILABLE_IN_TICKS")
        if execution["entry_after_signal_close"] is False:
            integrity_flags.append("FLAG_ENTRY_BEFORE_SIGNAL_CLOSE")
        if ticks.is_empty():
            integrity_flags.append("FLAG_MISSING_TICK_WINDOW")
        if _partials(trade.get("partial_exits")) and not r_audit["r_matches"]:
            integrity_flags.append("FLAG_PARTIAL_EXIT_R_ACCOUNTING_CHECK_REQUIRED")
        if trade["exit_reason"] == "trailing_stop" and not trade.get("stop_history"):
            integrity_flags.append("FLAG_TRAILING_STOP_LOGIC_CHECK_REQUIRED")
        risk_distance = r_audit["initial_risk_price_distance"]
        result = {
            **trade, **stop, **execution, **r_audit, **weekend,
            "actual_pnl_r": trade["pnl_r"],
            "expected_max_loss_r": -1.0,
            "r_slippage": trade["pnl_r"] + 1 if trade["exit_reason"] == "stop_loss" else None,
            "max_favourable_excursion_price": excursion.get("mfe"),
            "max_adverse_excursion_price": excursion.get("mae"),
            "max_favourable_excursion_r": excursion.get("mfe") / risk_distance if risk_distance and excursion else None,
            "max_adverse_excursion_r": excursion.get("mae") / risk_distance if risk_distance and excursion else None,
            "max_spread_during_trade_pips": excursion.get("max_spread"),
            "avg_spread_during_trade_pips": excursion.get("avg_spread"),
            "p95_spread_during_trade_pips": excursion.get("p95_spread"),
            "integrity_flags": integrity_flags,
        }
        self.stop_rows.append(stop)
        self.execution_rows.append(execution)
        self.r_rows.append(r_audit)
        self.weekend_rows.append(weekend)
        self.flags.extend({"trade_id": trade_id, "flag": flag} for flag in integrity_flags)
        return result

    def analyze_all_trades(self) -> list[dict]:
        self.results = []
        ids = self.trades["trade_id"].to_list()
        for index, trade_id in enumerate(ids, 1):
            if index == 1 or index % 25 == 0 or index == len(ids):
                logger.info("Forensic audit progress | trade=%s/%s", index, len(ids))
            self.results.append(self.analyze_single_trade(trade_id))
        return self.results

    def analyze_worst_trades(self, top_n: int) -> list[dict]:
        return sorted(self.results, key=lambda row: row["actual_pnl_r"])[:top_n]

    def analyze_best_trades(self, top_n: int) -> list[dict]:
        return sorted(self.results, key=lambda row: row["actual_pnl_r"], reverse=True)[:top_n]

    def _export_ticks(self, trade: dict, result: dict) -> None:
        cfg = self.forensic_config["output"]
        output = self.output / "tick_windows"
        output.mkdir(parents=True, exist_ok=True)
        ticks = self._ticks(trade, max(cfg["tick_window_minutes_before_entry"], cfg["tick_window_minutes_after_exit"]))
        if ticks.height > cfg["max_ticks_export_per_trade"]:
            step = max(1, ticks.height // cfg["max_ticks_export_per_trade"])
            ticks = ticks.gather_every(step)
        marker = (
            pl.when(pl.col("timestamp_utc") == trade["entry_timestamp_utc"]).then(pl.lit("ENTRY"))
            .when(pl.col("timestamp_utc") == trade["exit_timestamp_utc"]).then(pl.lit("EXIT"))
        )
        if result["initial_stop_first_cross_timestamp"] is not None:
            marker = marker.when(
                pl.col("timestamp_utc") == result["initial_stop_first_cross_timestamp"]
            ).then(pl.lit("STOP_CROSS"))
        if result["target_first_cross_timestamp"] is not None:
            marker = marker.when(
                pl.col("timestamp_utc") == result["target_first_cross_timestamp"]
            ).then(pl.lit("TARGET_CROSS"))
        ticks = ticks.with_columns(
            pl.lit(trade["final_stop"]).alias("active_stop"),
            pl.lit(trade["target_price"]).alias("active_target"),
            pl.lit(None, dtype=pl.Float64).alias("active_trailing_stop"),
            marker.otherwise(pl.lit("NONE")).alias("marker"),
        )
        base = output / f"trade_{trade['trade_id']}"
        ticks.write_csv(f"{base}_ticks_entry_to_exit.csv")
        ticks.filter(pl.col("timestamp_utc").is_between(
            trade["entry_timestamp_utc"] - timedelta(minutes=cfg["tick_window_minutes_before_entry"]),
            trade["entry_timestamp_utc"] + timedelta(minutes=cfg["tick_window_minutes_before_entry"]),
        )).write_csv(f"{base}_ticks_around_entry.csv")
        ticks.filter(pl.col("timestamp_utc").is_between(
            trade["exit_timestamp_utc"] - timedelta(minutes=cfg["tick_window_minutes_after_exit"]),
            trade["exit_timestamp_utc"] + timedelta(minutes=cfg["tick_window_minutes_after_exit"]),
        )).write_csv(f"{base}_ticks_around_exit.csv")
        if result["initial_stop_first_cross_timestamp"] is not None:
            cross = result["initial_stop_first_cross_timestamp"]
            minutes = cfg["tick_window_minutes_around_stop_cross"]
            ticks.filter(pl.col("timestamp_utc").is_between(
                cross - timedelta(minutes=minutes), cross + timedelta(minutes=minutes),
            )).write_csv(f"{base}_ticks_around_stop_cross.csv")

    def export_forensic_reports(self) -> dict:
        if not self.results:
            self.analyze_all_trades()
        top_cfg = self.forensic_config["worst_trade_analysis"]
        worst = self.analyze_worst_trades(top_cfg["top_n_worst_trades"])
        best = self.analyze_best_trades(top_cfg["top_n_best_trades"])
        for result in worst:
            trade = self.trades.filter(pl.col("trade_id") == result["trade_id"]).row(0, named=True)
            self._export_ticks(trade, result)
        critical = sum(flag["flag"] in {
            "FLAG_WRONG_BID_ASK_SIDE_POSSIBLE", "FLAG_ENTRY_BEFORE_SIGNAL_CLOSE",
            "FLAG_PARTIAL_EXIT_R_ACCOUNTING_CHECK_REQUIRED",
        } for flag in self.flags)
        worst_trade = worst[0]
        fail = critical or not worst_trade["exit_reason_matches_tick_path"]
        warning = any(row["actual_pnl_r"] < -2.5 or row["held_over_weekend"] for row in self.results)
        summary = {
            "total_trades": self.trades.height, "audited_trades": len(self.results),
            "worst_trade_id": worst_trade["trade_id"], "worst_trade_r": worst_trade["actual_pnl_r"],
            "worst_trade_exit_reason": worst_trade["actual_exit_reason"],
            "worst_trade_held_over_weekend": worst_trade["held_over_weekend"],
            "worst_trade_stop_crossed_before_exit": worst_trade["did_stop_cross_before_recorded_exit"],
            "worst_trade_expected_exit_reason": worst_trade["expected_exit_reason_if_first_barrier_wins"],
            "worst_trade_actual_exit_reason": worst_trade["actual_exit_reason"],
            "trades_loss_beyond_2_5r_count": sum(row["actual_pnl_r"] < -2.5 for row in self.results),
            "trades_loss_beyond_5r_count": sum(row["actual_pnl_r"] < -5 for row in self.results),
            "stop_cross_mismatch_count": sum(
                row["did_stop_cross_before_recorded_exit"] or not row["exit_reason_matches_tick_path"]
                for row in self.results
            ),
            "target_cross_mismatch_count": sum("FLAG_TARGET_CROSSED_BEFORE_EXIT_BUT_NOT_EXITED" in row["integrity_flags"] for row in self.results),
            "bid_ask_side_mismatch_count": sum("FLAG_WRONG_BID_ASK_SIDE_POSSIBLE" in row["integrity_flags"] for row in self.results),
            "entry_before_signal_count": sum("FLAG_ENTRY_BEFORE_SIGNAL_CLOSE" in row["integrity_flags"] for row in self.results),
            "missing_tick_window_count": sum("FLAG_MISSING_TICK_WINDOW" in row["integrity_flags"] for row in self.results),
            "weekend_held_trade_count": sum(row["held_over_weekend"] for row in self.results),
            "weekend_held_loss_count": sum(row["held_over_weekend"] and row["actual_pnl_r"] < 0 for row in self.results),
            "partial_exit_r_mismatch_count": sum("FLAG_PARTIAL_EXIT_R_ACCOUNTING_CHECK_REQUIRED" in row["integrity_flags"] for row in self.results),
            "critical_flag_count": critical, "warning_flag_count": len(self.flags) - critical,
            "final_status": "FAIL" if fail else ("WARNING" if warning else "PASS"),
        }
        write_rows(self.output / "worst_trades_forensics.csv", worst)
        write_rows(self.output / "best_trades_forensics.csv", best)
        write_rows(self.output / "stop_audit.csv", self.stop_rows)
        write_rows(self.output / "execution_audit.csv", self.execution_rows)
        write_rows(self.output / "r_multiple_audit.csv", self.r_rows)
        write_rows(self.output / "weekend_gap_audit.csv", self.weekend_rows)
        write_rows(self.output / "integrity_flags.csv", self.flags)
        write_forensic_report(self.output, summary, worst, self.flags)
        return summary

    def run(self) -> dict:
        with timed_stage(logger, "audit all trades", trades=self.trades.height):
            self.analyze_all_trades()
        with timed_stage(logger, "export forensic reports", output=self.output):
            return self.export_forensic_reports()
