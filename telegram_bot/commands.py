"""
Telegram command handling.

Runs in its own background thread, long-polling `getUpdates` and replying
to /status, /pairs, /lastsignal, /today, and /help.
"""

from __future__ import annotations

import threading
import time

from config import config
from storage import csv_logger
from storage.signal_store import signal_store
from telegram_bot import formatter
from telegram_bot.client import telegram_client
from utils.logger import get_logger

logger = get_logger("telegram_commands")


class CommandListener:
    def __init__(self, data_connected_fn) -> None:
        """
        `data_connected_fn` is a zero-arg callable returning bool, used so
        /status always reflects whether the market-data API is reachable.
        """
        self._data_connected_fn = data_connected_fn
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="telegram-commands", daemon=True)
        self._thread.start()
        logger.info("Telegram command listener started.")

    def stop(self) -> None:
        self._stop_event.set()

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                updates = telegram_client.get_updates(timeout=20)
                for update in updates:
                    self._handle_update(update)
            except Exception as exc:  # noqa: BLE001 - keep the listener alive no matter what
                logger.error("Error in command listener loop: %s", exc)
                time.sleep(5)

    def _handle_update(self, update: dict) -> None:
        message = update.get("message") or update.get("channel_post")
        if not message:
            return
        text = (message.get("text") or "").strip()
        chat_id = str(message.get("chat", {}).get("id", config.telegram_chat_id))

        if not text.startswith("/"):
            return

        command = text.split()[0].lower().lstrip("/").split("@")[0]
        logger.info("Received command: /%s", command)

        if command == "status":
            active = signal_store.get_all_active()
            reply = formatter.format_status_message(
                data_connected=self._data_connected_fn(),
                active_signal_count=len(active),
                symbols=config.symbols,
            )
        elif command == "pairs":
            reply = formatter.format_pairs_message(config.symbols, config.timeframes)
        elif command == "lastsignal":
            reply = formatter.format_last_signal_message(csv_logger.read_last_signal())
        elif command == "today":
            reply = formatter.format_today_message(csv_logger.read_today_signals())
        elif command == "help":
            reply = formatter.format_help_message()
        else:
            reply = "Unknown command. Send /help to see available commands."

        telegram_client.send_message(reply, chat_id=chat_id)
