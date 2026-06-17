import json
from types import SimpleNamespace

from src.broker.ig.telegram_controller import handle_update, webhook_path
from src.broker.ig.telegram_notifier import control_state, status_summary, write_control_state


def _update(text="/status", user_id=123):
    return {"message": {"text": text, "from": {"id": user_id}}}


def test_control_state_defaults_to_active(tmp_path):
    assert control_state(tmp_path / "missing.json") == "ACTIVE"


def test_write_control_state_round_trip(tmp_path):
    path = write_control_state(tmp_path / "control.json", "PAUSED", source="test")

    assert control_state(path) == "PAUSED"


def test_handle_update_rejects_non_admin(tmp_path):
    config = SimpleNamespace(
        telegram_admin_user_id="123",
        telegram_status_path=tmp_path / "status.json",
        telegram_control_path=tmp_path / "control.json",
    )

    response = handle_update(_update("/pause", 999), config)

    assert response == "Unauthorized user."
    assert control_state(config.telegram_control_path) == "ACTIVE"


def test_handle_update_writes_pause_resume_stop(tmp_path):
    config = SimpleNamespace(
        telegram_admin_user_id="123",
        telegram_status_path=tmp_path / "status.json",
        telegram_control_path=tmp_path / "control.json",
    )

    assert "PAUSED" in handle_update(_update("/pause"), config)
    assert control_state(config.telegram_control_path) == "PAUSED"
    assert "ACTIVE" in handle_update(_update("/resume"), config)
    assert control_state(config.telegram_control_path) == "ACTIVE"
    assert "stop requested" in handle_update(_update("/stop"), config).lower()
    assert control_state(config.telegram_control_path) == "STOP_REQUESTED"


def test_status_summary_reads_status_file(tmp_path):
    status = tmp_path / "bot_run.json"
    status.write_text(json.dumps({
        "status": "COMPLETED",
        "tick_count": 123,
        "last_evaluated_candle": "2026-06-17T18:00:00+00:00",
        "last_signal_result": {"status": "NO_SIGNAL"},
        "order_execution": None,
    }))

    summary = status_summary(status, tmp_path / "control.json")

    assert "run_status: COMPLETED" in summary
    assert "tick_count: 123" in summary
    assert "last_signal_status: NO_SIGNAL" in summary


def test_webhook_path_prefers_full_configured_path():
    config = SimpleNamespace(
        telegram_webhook_path="/telegram-webhook/prod-tg-secret-123",
        telegram_webhook_secret="ignored",
    )

    assert webhook_path(config) == "/telegram-webhook/prod-tg-secret-123"


def test_webhook_path_falls_back_to_secret():
    config = SimpleNamespace(telegram_webhook_path="", telegram_webhook_secret="secret")

    assert webhook_path(config) == "/telegram/secret"
