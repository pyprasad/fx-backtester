import csv
import json
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import product
from pathlib import Path
import re

import yaml

from src.backtest.backtest_engine import run_backtest
from src.config.config_loader import apply_weekend_policy_variant, load_strategy_config
from src.broker.ig.ig_live_signal import runtime_config_from_contract
from src.strategies.fx_swing_trend_reclaim import SIGNAL_TIMING_CANDLE_CLOSE
from src.utils.logging import get_logger


logger = get_logger(__name__)


SESSION_PRESETS = {
    "all": None,
    "tokyo": ["Tokyo"],
    "london_morning": ["London morning"],
    "overlap": ["London New York overlap"],
    "london_combined": ["London morning", "London New York overlap"],
}


@dataclass(frozen=True)
class CandleCloseCandidate:
    name: str
    direction_mode: str
    session_preset: str
    rsi_level: int
    pullback_atr: float
    fixed_take_profit_pips: float
    min_body_atr: float | None = None
    min_atr_pips: float | None = None
    allowed_signal_hours_utc: tuple[int, ...] | None = None

    def overrides(self) -> dict:
        return {
            "direction_mode": self.direction_mode,
            "session_preset": self.session_preset,
            "rsi_level": self.rsi_level,
            "pullback_atr": self.pullback_atr,
            "fixed_take_profit_pips": self.fixed_take_profit_pips,
            "min_body_atr": self.min_body_atr,
            "min_atr_pips": self.min_atr_pips,
            "allowed_signal_hours_utc": (
                ",".join(str(hour) for hour in self.allowed_signal_hours_utc)
                if self.allowed_signal_hours_utc else ""
            ),
        }


def _safe(value) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", str(value)).strip("_").lower().replace(".", "_")


def build_candidates(
    *,
    direction_modes: list[str] | None = None,
    session_presets: list[str] | None = None,
    rsi_levels: list[int] | None = None,
    pullback_atrs: list[float] | None = None,
    fixed_take_profit_pips: list[float] | None = None,
    min_body_atrs: list[float | None] | None = None,
    min_atr_pips_values: list[float | None] | None = None,
    hour_presets: dict[str, tuple[int, ...] | None] | None = None,
) -> list[CandleCloseCandidate]:
    direction_modes = direction_modes or ["long_short", "long_only", "short_only"]
    session_presets = session_presets or ["all", "tokyo", "london_morning", "overlap", "london_combined"]
    rsi_levels = rsi_levels or [45, 50, 55]
    pullback_atrs = pullback_atrs or [0.8, 1.0, 1.2]
    fixed_take_profit_pips = fixed_take_profit_pips or [6.0, 8.0, 10.0]
    min_body_atrs = min_body_atrs or [None]
    min_atr_pips_values = min_atr_pips_values or [None]
    hour_presets = hour_presets or {"all_hours": None}

    candidates = []
    for direction, session, rsi, pullback, target, min_body, min_atr, hour_name in product(
        direction_modes, session_presets, rsi_levels, pullback_atrs,
        fixed_take_profit_pips, min_body_atrs, min_atr_pips_values, hour_presets
    ):
        if session not in SESSION_PRESETS:
            raise ValueError(f"Unknown session preset: {session}")
        hours = hour_presets[hour_name]
        name = (
            f"{_safe(direction)}_{_safe(session)}_rsi{_safe(rsi)}_"
            f"pullback{_safe(pullback)}_tp{_safe(target)}_"
            f"body{_safe(min_body if min_body is not None else 'none')}_"
            f"atr{_safe(min_atr if min_atr is not None else 'none')}_hours{_safe(hour_name)}"
        )
        candidates.append(CandleCloseCandidate(name, direction, session, rsi, pullback, target, min_body, min_atr, hours))
    return candidates


def apply_candidate(config, candidate: CandleCloseCandidate):
    result = deepcopy(config)
    result.execution["signal_timing_mode"] = SIGNAL_TIMING_CANDLE_CLOSE
    result.entry["long"]["enabled"] = candidate.direction_mode in {"long_only", "long_short"}
    result.entry["short"]["enabled"] = candidate.direction_mode in {"short_only", "long_short"}
    result.entry["long"]["rsi_cross_up_level"] = candidate.rsi_level
    result.entry["short"]["rsi_cross_down_level"] = candidate.rsi_level
    result.entry["long"]["max_pullback_atr"] = candidate.pullback_atr
    result.entry["short"]["max_pullback_atr"] = candidate.pullback_atr
    quality_enabled = (
        candidate.min_body_atr is not None
        or candidate.min_atr_pips is not None
        or candidate.allowed_signal_hours_utc is not None
    )
    result.entry["quality_filters"] = {
        "enabled": quality_enabled,
        "min_body_atr": candidate.min_body_atr,
        "min_atr_pips": candidate.min_atr_pips,
        "allowed_signal_hours_utc": list(candidate.allowed_signal_hours_utc or []),
    }
    result.exit["fixed_take_profit"] = {
        "enabled": True,
        "target_pips": float(candidate.fixed_take_profit_pips),
        "execution_mode": "attached_limit",
        "disable_partial_take_profit": True,
        "disable_move_stop_to_breakeven": True,
        "disable_runner": True,
    }
    result.exit["partial_take_profit"]["enabled"] = False
    result.exit["move_stop_to_breakeven"]["enabled"] = False
    result.exit["runner"]["enabled"] = False
    allowed_sessions = SESSION_PRESETS[candidate.session_preset]
    if allowed_sessions is not None:
        result.session_filter["entry_windows"] = [
            item for item in result.session_filter["entry_windows"]
            if item["name"] in allowed_sessions
        ]
    return result


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("")
        return
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _score(metrics: dict) -> float:
    if metrics.get("total_trades", 0) < 100:
        return -10_000
    return round(
        float(metrics.get("total_return_percent", 0))
        + float(metrics.get("profit_factor", 0)) * 25
        - float(metrics.get("max_drawdown_percent", 0)) * 5,
        4,
    )


class CandleCloseSearchRunner:
    def __init__(
        self,
        *,
        strategy_config: str | Path,
        report_output_path: str | Path,
        normalised_tick_path: str | Path | None = None,
        candle_path: str | Path | None = None,
        strategy_contract_config: str | Path | None = None,
        news_calendar_file: str | Path | None = None,
        max_variants: int = 50,
        continue_on_error: bool = True,
        direction_modes: list[str] | None = None,
        session_presets: list[str] | None = None,
        rsi_levels: list[int] | None = None,
        pullback_atrs: list[float] | None = None,
        fixed_take_profit_pips: list[float] | None = None,
        min_body_atrs: list[float | None] | None = None,
        min_atr_pips_values: list[float | None] | None = None,
        hour_presets: dict[str, tuple[int, ...] | None] | None = None,
    ):
        self.strategy_config = Path(strategy_config)
        self.strategy_contract_config = Path(strategy_contract_config) if strategy_contract_config else None
        self.report_parent = Path(report_output_path).resolve()
        self.normalised_tick_path = str(Path(normalised_tick_path).resolve()) if normalised_tick_path else None
        self.candle_path = str(Path(candle_path).resolve()) if candle_path else None
        self.news_calendar_file = str(news_calendar_file) if news_calendar_file else None
        self.max_variants = max_variants
        self.continue_on_error = continue_on_error
        self.direction_modes = direction_modes
        self.session_presets = session_presets
        self.rsi_levels = rsi_levels
        self.pullback_atrs = pullback_atrs
        self.fixed_take_profit_pips = fixed_take_profit_pips
        self.min_body_atrs = min_body_atrs
        self.min_atr_pips_values = min_atr_pips_values
        self.hour_presets = hour_presets
        self.output = self.report_parent / datetime.now(timezone.utc).strftime(
            "candle_close_search_%Y%m%d_%H%M%S"
        )

    def _base_config(self):
        if self.strategy_contract_config:
            config, _contract = runtime_config_from_contract(self.strategy_contract_config, self.strategy_config)
        else:
            config = load_strategy_config(self.strategy_config)
        if self.normalised_tick_path:
            config.data["normalised_tick_path"] = self.normalised_tick_path
        if self.candle_path:
            config.data["candle_path"] = self.candle_path
        if self.news_calendar_file:
            config.news_guard["calendar_file"] = self.news_calendar_file
        config.execution["signal_timing_mode"] = SIGNAL_TIMING_CANDLE_CLOSE
        return apply_weekend_policy_variant(config, "force_close_friday_20_30", "config/weekend_policy_variants.usdjpy.yaml")

    def run(self) -> Path:
        self.output.mkdir(parents=True, exist_ok=True)
        base = self._base_config()
        candidates = build_candidates(
            direction_modes=self.direction_modes,
            session_presets=self.session_presets,
            rsi_levels=self.rsi_levels,
            pullback_atrs=self.pullback_atrs,
            fixed_take_profit_pips=self.fixed_take_profit_pips,
            min_body_atrs=self.min_body_atrs,
            min_atr_pips_values=self.min_atr_pips_values,
            hour_presets=self.hour_presets,
        )[:self.max_variants]
        rows = []
        for index, candidate in enumerate(candidates, start=1):
            folder = self.output / "variants" / candidate.name
            folder.mkdir(parents=True, exist_ok=True)
            logger.info("Candle-close candidate %s/%s | name=%s", index, len(candidates), candidate.name)
            try:
                config = apply_candidate(base, candidate)
                snapshot = config.model_dump(exclude={"base_dir"}, mode="json")
                (folder / "variant_config_snapshot.yaml").write_text(yaml.safe_dump(snapshot, sort_keys=False))
                _trades, metrics, _output = run_backtest(config, output_override=folder)
                row = {
                    "variant_name": candidate.name,
                    "run_status": "SUCCESS",
                    "error_message": "",
                    **candidate.overrides(),
                    **metrics,
                    "candidate_score": _score(metrics),
                    "report_path": str(folder),
                }
            except Exception as exc:
                logger.exception("Candle-close candidate failed | name=%s", candidate.name)
                row = {
                    "variant_name": candidate.name,
                    "run_status": "ERROR",
                    "error_message": str(exc),
                    **candidate.overrides(),
                    "candidate_score": -10_000,
                    "report_path": str(folder),
                }
                if not self.continue_on_error:
                    raise
            rows.append(row)
            (folder / "variant_metadata.json").write_text(json.dumps(row, indent=2, default=str))

        ranked = sorted(
            rows,
            key=lambda row: (
                row.get("run_status") == "SUCCESS",
                row.get("candidate_score", -10_000),
                row.get("total_return_percent", -10_000),
                row.get("profit_factor", 0),
                -row.get("max_drawdown_percent", 100),
            ),
            reverse=True,
        )
        _write_csv(self.output / "candle_close_search_summary.csv", rows)
        _write_csv(self.output / "candle_close_search_ranked.csv", ranked)
        (self.output / "candle_close_search_summary.json").write_text(json.dumps(rows, indent=2, default=str))
        (self.output / "candle_close_search_ranked.json").write_text(json.dumps(ranked, indent=2, default=str))
        logger.info("Candle-close search complete | output=%s", self.output)
        return self.output
