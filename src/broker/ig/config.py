import os
import warnings
from dataclasses import dataclass, replace
from pathlib import Path

from .models import redact

DEMO_REST_BASE_URL = "https://demo-api.ig.com/gateway/deal"
LIVE_REST_BASE_URL = "https://api.ig.com/gateway/deal"


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
    historical_api_key: str = ""
    historical_username: str = ""
    historical_password: str = ""
    historical_account_id: str = ""
    historical_token_cache_enabled: bool = False
    historical_token_cache_path: Path = Path(".runtime/ig_demo_historical_session.json")
    news_guard_calendar_refresh_enabled: bool = True
    news_guard_calendar_forward_days: int = 21
    news_guard_calendar_min_forward_days: int = 7
    news_guard_calendar_refresh_minutes_before_session: int = 30
    news_guard_calendar_prune_retention_hours: int = 24
    news_guard_calendar_cache_dir: Path = Path("data/macro_calendar/cache/nasdaq_live")
    telegram_enabled: bool = False
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    telegram_notify_trades: bool = True
    telegram_notify_system: bool = True
    telegram_webhook_secret: str = ""
    telegram_webhook_path: str = ""
    telegram_admin_user_id: str = ""
    telegram_control_path: Path = Path(".runtime/ig_bot_control.json")
    telegram_status_path: Path = Path("reports/ig_demo_audit/bot_run_usdjpy.json")

    def redacted(self) -> dict:
        return {
            "env": self.env, "api_key": redact(self.api_key), "username": redact(self.username),
            "password": "***", "account_id": redact(self.account_id), "acc_type": self.acc_type,
            "rest_base_url": self.rest_base_url, "streaming_enabled": self.streaming_enabled,
            "streaming_mode": self.streaming_mode, "order_execution_enabled": self.order_execution_enabled,
            "dry_run_only": self.dry_run_only, "price_scale_divisor": self.price_scale_divisor,
            "historical_data_override_enabled": self.historical_data_override_enabled,
            "historical_username": redact(self.historical_username),
            "telegram_enabled": self.telegram_enabled,
            "telegram_chat_id": redact(self.telegram_chat_id),
            "telegram_admin_user_id": redact(self.telegram_admin_user_id),
        }

    def __repr__(self) -> str:
        return f"IGDemoConfig({self.redacted()!r})"

    @property
    def historical_data_override_enabled(self) -> bool:
        return bool(self.historical_api_key or self.historical_username or self.historical_password)

    @property
    def is_demo(self) -> bool:
        return self.env == "DEMO" and self.acc_type == "DEMO"

    @property
    def is_live(self) -> bool:
        return self.env == "LIVE" and self.acc_type == "LIVE"

    def historical_data_config(self) -> "IGDemoConfig":
        if not all((self.historical_api_key, self.historical_username, self.historical_password)):
            raise ValueError(
                "IG_HISTORICAL_API_KEY, IG_HISTORICAL_USERNAME, and "
                "IG_HISTORICAL_PASSWORD must all be set for historical override"
            )
        return replace(
            self,
            api_key=self.historical_api_key,
            username=self.historical_username,
            password=self.historical_password,
            account_id=self.historical_account_id,
            order_execution_enabled=False,
            dry_run_only=True,
            token_cache_enabled=self.historical_token_cache_enabled,
            token_cache_path=self.historical_token_cache_path,
        )


def load_ig_demo_config(env_file: str | None = None, require_credentials: bool = True) -> IGDemoConfig:
    values = {**_env_file(env_file), **os.environ}
    def get(key, default=""):
        return values.get(key, default)

    config = IGDemoConfig(
        env=get("IG_ENV", "DEMO").upper(), api_key=get("IG_API_KEY"), username=get("IG_USERNAME"),
        password=get("IG_PASSWORD"), account_id=get("IG_ACCOUNT_ID"), acc_type=get("IG_ACC_TYPE", "DEMO").upper(),
        rest_base_url=get("IG_REST_BASE_URL", DEMO_REST_BASE_URL).rstrip("/"),
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
        historical_api_key=get("IG_HISTORICAL_API_KEY"),
        historical_username=get("IG_HISTORICAL_USERNAME"),
        historical_password=get("IG_HISTORICAL_PASSWORD"),
        historical_account_id=get("IG_HISTORICAL_ACCOUNT_ID"),
        historical_token_cache_enabled=_bool(
            get("IG_HISTORICAL_TOKEN_CACHE_ENABLED", get("IG_TOKEN_CACHE_ENABLED", "false")),
            False,
        ),
        historical_token_cache_path=Path(
            get("IG_HISTORICAL_TOKEN_CACHE_PATH", ".runtime/ig_demo_historical_session.json")
        ),
        news_guard_calendar_refresh_enabled=_bool(get("NEWS_GUARD_CALENDAR_REFRESH_ENABLED", "true"), True),
        news_guard_calendar_forward_days=int(get("NEWS_GUARD_FORWARD_DAYS", "21")),
        news_guard_calendar_min_forward_days=int(get("NEWS_GUARD_MIN_FORWARD_DAYS", "7")),
        news_guard_calendar_refresh_minutes_before_session=int(
            get("NEWS_GUARD_REFRESH_MINUTES_BEFORE_SESSION", "30")
        ),
        news_guard_calendar_prune_retention_hours=int(get("NEWS_GUARD_PRUNE_RETENTION_HOURS", "24")),
        news_guard_calendar_cache_dir=Path(get("NEWS_GUARD_CACHE_DIR", "data/macro_calendar/cache/nasdaq_live")),
        telegram_enabled=_bool(get("TELEGRAM_ENABLED", "false"), False),
        telegram_bot_token=get("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=get("TELEGRAM_CHAT_ID"),
        telegram_notify_trades=_bool(get("TELEGRAM_NOTIFY_TRADES", "true"), True),
        telegram_notify_system=_bool(get("TELEGRAM_NOTIFY_SYSTEM", "true"), True),
        telegram_webhook_secret=get("TELEGRAM_WEBHOOK_SECRET"),
        telegram_webhook_path=get("TELEGRAM_WEBHOOK_PATH"),
        telegram_admin_user_id=get("TELEGRAM_ADMIN_USER_ID"),
        telegram_control_path=Path(get("TELEGRAM_CONTROL_PATH", ".runtime/ig_bot_control.json")),
        telegram_status_path=Path(get("TELEGRAM_STATUS_PATH", "reports/ig_demo_audit/bot_run_usdjpy.json")),
    )
    if config.env not in {"DEMO", "LIVE"}:
        raise ValueError("IG_ENV must be DEMO or LIVE")
    if config.acc_type not in {"DEMO", "LIVE"}:
        raise ValueError("IG_ACC_TYPE must be DEMO or LIVE")
    if config.env != config.acc_type:
        raise ValueError("IG_ENV and IG_ACC_TYPE must match")
    expected_gateway = DEMO_REST_BASE_URL if config.is_demo else LIVE_REST_BASE_URL
    if config.rest_base_url != expected_gateway:
        raise ValueError(f"IG_REST_BASE_URL must be {expected_gateway} for {config.env}")
    if config.order_execution_enabled == config.dry_run_only:
        raise ValueError(
            "IG_ORDER_EXECUTION_ENABLED and IG_DRY_RUN_ONLY must be opposite values"
        )
    if config.streaming_mode == "MARKET":
        raise ValueError("MARKET subscription is deprecated; use PRICE or CHART_TICK")
    if config.price_scale_divisor is not None and config.price_scale_divisor <= 0:
        raise ValueError("IG_PRICE_SCALE_DIVISOR must be greater than zero")
    if config.news_guard_calendar_forward_days < config.news_guard_calendar_min_forward_days:
        raise ValueError("NEWS_GUARD_FORWARD_DAYS must be >= NEWS_GUARD_MIN_FORWARD_DAYS")
    if config.news_guard_calendar_min_forward_days < 1:
        raise ValueError("NEWS_GUARD_MIN_FORWARD_DAYS must be at least 1")
    if config.news_guard_calendar_refresh_minutes_before_session < 0:
        raise ValueError("NEWS_GUARD_REFRESH_MINUTES_BEFORE_SESSION must be >= 0")
    if config.news_guard_calendar_prune_retention_hours < 1:
        raise ValueError("NEWS_GUARD_PRUNE_RETENTION_HOURS must be at least 1")
    if config.historical_data_override_enabled and not all((
        config.historical_api_key, config.historical_username, config.historical_password,
    )):
        raise ValueError(
            "Set all or none of IG_HISTORICAL_API_KEY, IG_HISTORICAL_USERNAME, "
            "and IG_HISTORICAL_PASSWORD"
        )
    if require_credentials and not all((config.api_key, config.username, config.password)):
        raise ValueError(f"IG {config.env} API key, username, and password are required")
    if config.telegram_enabled and not all((config.telegram_bot_token, config.telegram_chat_id)):
        raise ValueError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are required when TELEGRAM_ENABLED=true")
    if not config.account_id:
        warnings.warn("IG_ACCOUNT_ID is missing; /accounts may be used to resolve it", stacklevel=2)
    return config
