import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from queue import Empty, Queue
from threading import Thread
from urllib.parse import urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self, config):
        self.enabled = bool(getattr(config, "telegram_enabled", False))
        self.bot_token = getattr(config, "telegram_bot_token", "")
        self.chat_id = getattr(config, "telegram_chat_id", "")
        self.notify_trades = bool(getattr(config, "telegram_notify_trades", True))
        self.notify_system = bool(getattr(config, "telegram_notify_system", True))
        self.queue: Queue[dict] = Queue(maxsize=100)
        self.running = False
        self.worker: Thread | None = None
        if self.enabled and self.bot_token and self.chat_id:
            self.running = True
            self.worker = Thread(target=self._worker_loop, daemon=True)
            self.worker.start()

    def send(self, text: str, *, category: str = "system") -> None:
        if not self.enabled:
            return
        if category == "system" and not self.notify_system:
            return
        if category == "trade" and not self.notify_trades:
            return
        try:
            self.queue.put_nowait({"text": text})
        except Exception as exc:
            logger.debug("Telegram queue failed: %s", exc)

    def close(self, timeout_seconds: float = 3.0) -> None:
        deadline = time.monotonic() + timeout_seconds
        while not self.queue.empty() and time.monotonic() < deadline:
            time.sleep(0.05)
        self.running = False

    def _worker_loop(self) -> None:
        while self.running:
            try:
                payload = self.queue.get(timeout=1.0)
            except Empty:
                continue
            try:
                send_telegram_message(self.bot_token, self.chat_id, payload["text"])
            except Exception as exc:
                logger.warning("Telegram notification failed: %s", exc)
            finally:
                self.queue.task_done()


def send_telegram_message(bot_token: str, chat_id: str, text: str) -> dict:
    body = urlencode({
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": "true",
    }).encode()
    request = Request(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        data=body,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urlopen(request, timeout=10) as response:
        content = response.read()
        return json.loads(content) if content else {}


def write_control_state(path: str | Path, state: str, *, source: str, message: str = "") -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "state": state,
        "source": source,
        "message": message,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }, indent=2))
    return path


def read_control_state(path: str | Path) -> dict:
    path = Path(path)
    if not path.exists():
        return {"state": "ACTIVE"}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {"state": "ACTIVE", "error": "INVALID_CONTROL_FILE"}


def control_state(path: str | Path) -> str:
    return str(read_control_state(path).get("state") or "ACTIVE").upper()


def status_summary(status_path: str | Path, control_path: str | Path) -> str:
    control = read_control_state(control_path)
    lines = [
        "USDJPY bot status",
        f"control: {control.get('state', 'ACTIVE')}",
        f"control_updated_at: {control.get('updated_at', 'n/a')}",
    ]
    path = Path(status_path)
    if path.exists():
        try:
            status = json.loads(path.read_text())
            lines.extend([
                f"run_status: {status.get('status')}",
                f"tick_count: {status.get('tick_count')}",
                f"last_evaluated_candle: {status.get('last_evaluated_candle')}",
                f"last_signal_status: {(status.get('last_signal_result') or {}).get('status')}",
                f"order_sent: {bool(status.get('order_execution'))}",
            ])
        except (json.JSONDecodeError, OSError):
            lines.append("run_status: status file unreadable")
    else:
        lines.append("run_status: no status file yet")
    return "\n".join(lines)


def sleep_briefly(seconds: float) -> None:
    time.sleep(seconds)
