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


def test_rejects_live_and_execution_enabled(tmp_path, monkeypatch):
    monkeypatch.delenv("IG_ENV", raising=False)
    with pytest.raises(ValueError, match="DEMO only"):
        load_ig_demo_config(_env(tmp_path, IG_ENV="LIVE"))
    with pytest.raises(ValueError, match="order execution disabled"):
        load_ig_demo_config(_env(tmp_path, IG_ORDER_EXECUTION_ENABLED="true"))
    with pytest.raises(ValueError, match="MARKET subscription is deprecated"):
        load_ig_demo_config(_env(tmp_path, IG_STREAMING_MODE="MARKET"))
    with pytest.raises(ValueError, match="PRICE_SCALE_DIVISOR"):
        load_ig_demo_config(_env(tmp_path, IG_PRICE_SCALE_DIVISOR="0"))
