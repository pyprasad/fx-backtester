import pytest

from src.broker.ig.config import load_ig_demo_config


def _env(tmp_path, **overrides):
    values = {
        "IG_ENV": "DEMO", "IG_ACC_TYPE": "DEMO", "IG_API_KEY": "secret-api-key",
        "IG_USERNAME": "demo-user", "IG_PASSWORD": "secret-password",
        "IG_ORDER_EXECUTION_ENABLED": "false", "IG_DRY_RUN_ONLY": "true",
    }
    values.update(overrides)
    path = tmp_path / ".env"
    path.write_text("\n".join(f"{key}={value}" for key, value in values.items()))
    return path


def test_loads_demo_and_redacts_secrets(tmp_path, monkeypatch):
    for key in ("IG_ENV", "IG_ACC_TYPE", "IG_API_KEY", "IG_USERNAME", "IG_PASSWORD"):
        monkeypatch.delenv(key, raising=False)
    config = load_ig_demo_config(_env(tmp_path))
    text = repr(config)
    assert config.env == "DEMO"
    assert "secret-password" not in text
    assert "secret-api-key" not in text


def test_rejects_live_and_inconsistent_execution_flags(tmp_path, monkeypatch):
    monkeypatch.delenv("IG_ENV", raising=False)
    with pytest.raises(ValueError, match="DEMO only"):
        load_ig_demo_config(_env(tmp_path, IG_ENV="LIVE"))
    with pytest.raises(ValueError, match="DEMO gateway"):
        load_ig_demo_config(_env(
            tmp_path, IG_REST_BASE_URL="https://api.ig.com/gateway/deal"
        ))
    execution = load_ig_demo_config(_env(
        tmp_path, IG_ORDER_EXECUTION_ENABLED="true", IG_DRY_RUN_ONLY="false"
    ))
    assert execution.order_execution_enabled is True
    assert execution.dry_run_only is False
    with pytest.raises(ValueError, match="opposite values"):
        load_ig_demo_config(_env(tmp_path, IG_ORDER_EXECUTION_ENABLED="true"))
    with pytest.raises(ValueError, match="MARKET subscription is deprecated"):
        load_ig_demo_config(_env(tmp_path, IG_STREAMING_MODE="MARKET"))
    with pytest.raises(ValueError, match="PRICE_SCALE_DIVISOR"):
        load_ig_demo_config(_env(tmp_path, IG_PRICE_SCALE_DIVISOR="0"))


def test_optional_historical_credentials_are_separate_and_non_executable(tmp_path, monkeypatch):
    monkeypatch.delenv("IG_ENV", raising=False)
    config = load_ig_demo_config(_env(
        tmp_path,
        IG_HISTORICAL_API_KEY="hist-api",
        IG_HISTORICAL_USERNAME="hist-user",
        IG_HISTORICAL_PASSWORD="hist-password",
        IG_HISTORICAL_ACCOUNT_ID="HISTACC",
    ))
    historical = config.historical_data_config()

    assert config.api_key == "secret-api-key"
    assert config.username == "demo-user"
    assert historical.api_key == "hist-api"
    assert historical.username == "hist-user"
    assert historical.password == "hist-password"
    assert historical.account_id == "HISTACC"
    assert historical.order_execution_enabled is False
    assert historical.dry_run_only is True


def test_optional_telegram_config(tmp_path, monkeypatch):
    monkeypatch.delenv("IG_ENV", raising=False)
    config = load_ig_demo_config(_env(
        tmp_path,
        TELEGRAM_ENABLED="true",
        TELEGRAM_BOT_TOKEN="bot-token",
        TELEGRAM_CHAT_ID="chat-id",
        TELEGRAM_ADMIN_USER_ID="123",
        TELEGRAM_WEBHOOK_SECRET="secret-path",
        TELEGRAM_WEBHOOK_PATH="/telegram-webhook/prod-tg-secret-123",
    ))

    assert config.telegram_enabled is True
    assert config.telegram_bot_token == "bot-token"
    assert config.telegram_chat_id == "chat-id"
    assert config.telegram_admin_user_id == "123"
    assert config.telegram_webhook_secret == "secret-path"
    assert config.telegram_webhook_path == "/telegram-webhook/prod-tg-secret-123"


def test_rejects_partial_historical_credentials(tmp_path, monkeypatch):
    monkeypatch.delenv("IG_ENV", raising=False)
    with pytest.raises(ValueError, match="Set all or none"):
        load_ig_demo_config(_env(tmp_path, IG_HISTORICAL_USERNAME="hist-user"))
