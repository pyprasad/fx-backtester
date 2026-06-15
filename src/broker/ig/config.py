import os
import warnings
from dataclasses import dataclass
from pathlib import Path

from .models import redact


def _bool(value: str | bool | None, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if value.lower() in {"true", "1", "yes"}:
        return True
    if value.lower() in {"false", "0", "no"}:
        return False
    raise ValueError(f"Invalid boolean value: {value}")


def _env_file(path: str | None) -> dict[str, str]:
    if not path:
        return {}
    result = {}
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            result[key.strip()] = value.strip().strip("'\"")
    return result


@dataclass(repr=False)
class IGDemoConfig:
    env: str
    api_key: str
    username: str
    password: str
    account_id: str
    acc_type: str
    rest_base_url: str
    streaming_enabled: bool
    streaming_mode: str
    market_search_term: str
    market_epic: str
    order_execution_enabled: bool
    dry_run_only: bool
    tick_output_path: Path
    audit_output_path: Path
    log_level: str
    session_version: int = 2
    stream_price_fields: tuple[str, ...] = ()
    stream_chart_tick_fields: tuple[str, ...] = ()
    token_cache_enabled: bool = False
    token_cache_path: Path = Path(".runtime/ig_demo_session.json")
    price_scale_divisor: float | None = None

    def redacted(self) -> dict:
        return {
            "env": self.env, "api_key": redact(self.api_key), "username": redact(self.username),
            "password": "***", "account_id": redact(self.account_id), "acc_type": self.acc_type,
            "rest_base_url": self.rest_base_url, "streaming_enabled": self.streaming_enabled,
            "streaming_mode": self.streaming_mode, "order_execution_enabled": self.order_execution_enabled,
            "dry_run_only": self.dry_run_only, "price_scale_divisor": self.price_scale_divisor,
        }

    def __repr__(self) -> str:
        return f"IGDemoConfig({self.redacted()!r})"


def load_ig_demo_config(env_file: str | None = None, require_credentials: bool = True) -> IGDemoConfig:
    values = {**_env_file(env_file), **os.environ}
    def get(key, default=""):
        return values.get(key, default)

    config = IGDemoConfig(
        env=get("IG_ENV", "DEMO").upper(), api_key=get("IG_API_KEY"), username=get("IG_USERNAME"),
        password=get("IG_PASSWORD"), account_id=get("IG_ACCOUNT_ID"), acc_type=get("IG_ACC_TYPE", "DEMO").upper(),
        rest_base_url=get("IG_REST_BASE_URL", "https://demo-api.ig.com/gateway/deal").rstrip("/"),
        streaming_enabled=_bool(get("IG_STREAMING_ENABLED", "true"), True),
        streaming_mode=get("IG_STREAMING_MODE", "PRICE").upper(),
        market_search_term=get("IG_MARKET_SEARCH_TERM", "USD/JPY"), market_epic=get("IG_MARKET_EPIC"),
        order_execution_enabled=_bool(get("IG_ORDER_EXECUTION_ENABLED", "false"), False),
        dry_run_only=_bool(get("IG_DRY_RUN_ONLY", "true"), True),
        tick_output_path=Path(get("IG_TICK_OUTPUT_PATH", "data/live_demo_ticks/usdjpy")),
        audit_output_path=Path(get("IG_AUDIT_OUTPUT_PATH", "reports/ig_demo_audit")),
        log_level=get("IG_LOG_LEVEL", "INFO"), session_version=int(get("IG_USE_SESSION_VERSION", "2")),
        stream_price_fields=tuple(get("IG_STREAM_PRICE_FIELDS", "BIDPRICE1,ASKPRICE1,TIMESTAMP,DELAY,DLG_FLAG,HIGH,LOW,MID_OPEN").split(",")),
        stream_chart_tick_fields=tuple(get("IG_STREAM_CHART_TICK_FIELDS", "BID,OFR,LTP,UTM").split(",")),
        token_cache_enabled=_bool(get("IG_TOKEN_CACHE_ENABLED", "false"), False),
        token_cache_path=Path(get("IG_TOKEN_CACHE_PATH", ".runtime/ig_demo_session.json")),
        price_scale_divisor=float(get("IG_PRICE_SCALE_DIVISOR")) if get("IG_PRICE_SCALE_DIVISOR") else None,
    )
    if config.env != "DEMO" or config.acc_type != "DEMO":
        raise ValueError("FX-2I supports IG DEMO only")
    if config.rest_base_url != "https://demo-api.ig.com/gateway/deal":
        raise ValueError("IG_REST_BASE_URL must be the IG DEMO gateway")
    if config.order_execution_enabled == config.dry_run_only:
        raise ValueError(
            "IG_ORDER_EXECUTION_ENABLED and IG_DRY_RUN_ONLY must be opposite values"
        )
    if config.streaming_mode == "MARKET":
        raise ValueError("MARKET subscription is deprecated; use PRICE or CHART_TICK")
    if config.price_scale_divisor is not None and config.price_scale_divisor <= 0:
        raise ValueError("IG_PRICE_SCALE_DIVISOR must be greater than zero")
    if require_credentials and not all((config.api_key, config.username, config.password)):
        raise ValueError("IG DEMO API key, username, and password are required")
    if not config.account_id:
        warnings.warn("IG_ACCOUNT_ID is missing; /accounts may be used to resolve it", stacklevel=2)
    return config
