import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .config import load_ig_demo_config
from .telegram_notifier import send_telegram_message, status_summary, write_control_state

logger = logging.getLogger(__name__)


HELP_TEXT = "\n".join([
    "USDJPY bot commands:",
    "/status - show bot/control state",
    "/pause - pause new signal evaluation/order placement",
    "/resume - resume normal operation",
    "/stop - request graceful bot stop",
    "/help - show commands",
])


def _sender_id(update: dict) -> str:
    message = update.get("message") or update.get("edited_message") or {}
    sender = message.get("from") or {}
    return str(sender.get("id") or "")


def _message_text(update: dict) -> str:
    message = update.get("message") or update.get("edited_message") or {}
    return str(message.get("text") or "").strip()


def handle_update(update: dict, config) -> str:
    admin = str(config.telegram_admin_user_id or "")
    if admin and _sender_id(update) != admin:
        return "Unauthorized user."
    text = _message_text(update).split()[0].lower()
    if text in {"/help", "help"}:
        return HELP_TEXT
    if text in {"/status", "status"}:
        return status_summary(config.telegram_status_path, config.telegram_control_path)
    if text in {"/pause", "pause"}:
        write_control_state(config.telegram_control_path, "PAUSED", source="telegram", message=text)
        return "Bot control state set to PAUSED. New signal evaluation/order placement is paused."
    if text in {"/resume", "resume"}:
        write_control_state(config.telegram_control_path, "ACTIVE", source="telegram", message=text)
        return "Bot control state set to ACTIVE."
    if text in {"/stop", "stop"}:
        write_control_state(config.telegram_control_path, "STOP_REQUESTED", source="telegram", message=text)
        return "Graceful stop requested. The bot will exit on its next control check."
    return HELP_TEXT


def webhook_path(config) -> str:
    configured_path = str(getattr(config, "telegram_webhook_path", "") or "").strip()
    if configured_path:
        return configured_path if configured_path.startswith("/") else f"/{configured_path}"
    secret = str(getattr(config, "telegram_webhook_secret", "") or "").strip()
    if not secret:
        raise ValueError("TELEGRAM_WEBHOOK_PATH or TELEGRAM_WEBHOOK_SECRET is required for the Telegram controller")
    return f"/telegram/{secret}"


def run_webhook_controller(env_file: str | None, host: str, port: int) -> None:
    config = load_ig_demo_config(env_file, require_credentials=False)
    if not config.telegram_enabled:
        raise ValueError("TELEGRAM_ENABLED must be true for the Telegram controller")

    expected_path = webhook_path(config)

    class Handler(BaseHTTPRequestHandler):
        def _write(self, status: int, payload: dict) -> None:
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path == "/health":
                self._write(200, {"status": "healthy", "webhook_path": expected_path})
            else:
                self._write(404, {"error": "not found"})

        def do_POST(self):
            parsed = urlparse(self.path)
            if parsed.path != expected_path:
                self._write(404, {"error": "not found"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                update = json.loads(self.rfile.read(length) or b"{}")
                response = handle_update(update, config)
                send_telegram_message(config.telegram_bot_token, config.telegram_chat_id, response)
                self._write(200, {"status": "ok"})
            except Exception as exc:
                logger.exception("Telegram webhook failed")
                self._write(200, {"status": "error", "message": str(exc)})

        def log_message(self, fmt, *args):
            logger.info("telegram_webhook " + fmt, *args)

    Path(config.telegram_control_path).parent.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((host, port), Handler)
    logger.info("Telegram webhook controller listening on %s:%s%s", host, port, expected_path)
    server.serve_forever()
