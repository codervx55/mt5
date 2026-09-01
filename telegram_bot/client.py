"""Minimal Telegram Bot API client using `requests` only (no paid SDKs)."""

from __future__ import annotations

from typing import Any, Optional

import requests

from config import config
from utils.logger import get_logger
from utils.retry import retry_with_backoff

logger = get_logger("telegram_client")

_API_BASE = "https://api.telegram.org/bot{token}/{method}"


class TelegramError(Exception):
    """Raised when the Telegram API returns an error or is unreachable."""


class TelegramClient:
    def __init__(self, token: str | None = None, chat_id: str | None = None) -> None:
        self.token = token or config.telegram_bot_token
        self.chat_id = chat_id or config.telegram_chat_id
        self._last_update_id: Optional[int] = None

    def _url(self, method: str) -> str:
        return _API_BASE.format(token=self.token, method=method)

    @retry_with_backoff(max_attempts=4, base_delay=2, exceptions=(requests.RequestException, TelegramError))
    def send_message(self, text: str, chat_id: str | None = None, parse_mode: str = "HTML") -> dict:
        payload = {
            "chat_id": chat_id or self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }
        response = requests.post(self._url("sendMessage"), json=payload, timeout=15)
        data = response.json()
        if not data.get("ok"):
            raise TelegramError(f"sendMessage failed: {data}")
        return data

    def get_updates(self, timeout: int = 20) -> list[dict[str, Any]]:
        """Long-poll for new updates (commands) sent to the bot."""
        params = {"timeout": timeout}
        if self._last_update_id is not None:
            params["offset"] = self._last_update_id + 1

        try:
            response = requests.get(self._url("getUpdates"), params=params, timeout=timeout + 10)
            data = response.json()
        except requests.RequestException as exc:
            logger.warning("getUpdates failed: %s", exc)
            return []

        if not data.get("ok"):
            logger.warning("getUpdates returned error: %s", data)
            return []

        updates = data.get("result", [])
        if updates:
            self._last_update_id = updates[-1]["update_id"]
        return updates


telegram_client = TelegramClient()
