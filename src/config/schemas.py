from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict


class FlexibleConfig(BaseModel):
    model_config = ConfigDict(extra="allow")


class MarketConfig(FlexibleConfig):
    symbol: str = "USDJPY"
    pip_size: float = 0.01
    price_decimals: int = 3
    timezone: str = "UTC"


class DataQualityConfig(FlexibleConfig):
    market: MarketConfig
    input: dict[str, Any]
    validation: dict[str, Any]
    timestamp: dict[str, Any]
    price: dict[str, Any]
    spread: dict[str, Any]
    gaps: dict[str, Any]
    trading_hours: dict[str, Any]
    output: dict[str, Any]
    base_dir: Path = Path(".")


class StrategyConfig(FlexibleConfig):
    strategy: dict[str, Any]
    data: dict[str, Any]
    timeframes: dict[str, Any]
    candles: dict[str, Any]
    indicators: dict[str, Any]
    entry: dict[str, Any]
    risk: dict[str, Any]
    stop_loss: dict[str, Any]
    exit: dict[str, Any]
    session_filter: dict[str, Any]
    spread_filter: dict[str, Any]
    execution: dict[str, Any]
    reporting: dict[str, Any]
    forensics: dict[str, Any] = {}
    weekend_policy: dict[str, Any] = {}
    stability_validation: dict[str, Any] = {}
    walk_forward_validation: dict[str, Any] = {}
    parameter_robustness: dict[str, Any] = {}
    monte_carlo_stress: dict[str, Any] = {}
    broker_execution_guardrails: dict[str, Any] = {}
    position_sizing: dict[str, Any] = {}
    max_trade_duration_days: int = 7
    market_open_filter: dict[str, Any] = {}
    broker_guardrails: dict[str, Any] = {}
    time_guards: dict[str, Any] = {}
    config_path: Path | None = None
    base_dir: Path = Path(".")
