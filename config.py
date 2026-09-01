"""
Central configuration module.

Loads every setting from environment variables (via a `.env` file) so the
rest of the codebase never touches `os.environ` directly. Import `config`
(a singleton instance of `Config`) anywhere you need a setting.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List

from dotenv import load_dotenv

load_dotenv()


class ConfigError(Exception):
    """Raised when required configuration is missing or invalid."""


def _get_str(key: str, default: str | None = None, required: bool = False) -> str:
    value = os.getenv(key, default)
    if required and not value:
        raise ConfigError(f"Missing required environment variable: {key}")
    return value or ""


def _get_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"Environment variable {key} must be an integer, got {raw!r}") from exc


def _get_float(key: str, default: float) -> float:
    raw = os.getenv(key)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"Environment variable {key} must be a float, got {raw!r}") from exc


def _get_list(key: str, default: str) -> List[str]:
    raw = os.getenv(key, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass
class Config:
    # MT5
    mt5_login: str = field(default_factory=lambda: _get_str("MT5_LOGIN"))
    mt5_password: str = field(default_factory=lambda: _get_str("MT5_PASSWORD"))
    mt5_server: str = field(default_factory=lambda: _get_str("MT5_SERVER"))
    mt5_terminal_path: str = field(default_factory=lambda: _get_str("MT5_TERMINAL_PATH"))

    # Telegram
    telegram_bot_token: str = field(default_factory=lambda: _get_str("TELEGRAM_BOT_TOKEN", required=True))
    telegram_chat_id: str = field(default_factory=lambda: _get_str("TELEGRAM_CHAT_ID", required=True))

    # Pairs / timeframes
    symbols: List[str] = field(default_factory=lambda: _get_list("SYMBOLS", "BTCUSD,ETHUSD,XAUUSD"))
    timeframes: List[str] = field(default_factory=lambda: _get_list("TIMEFRAMES", "M5,M15"))
    confirmation_timeframe: str = field(default_factory=lambda: _get_str("CONFIRMATION_TIMEFRAME", "M15"))

    # Strategy
    risk_reward_ratio: float = field(default_factory=lambda: _get_float("RISK_REWARD_RATIO", 2.6))
    volume_lookback: int = field(default_factory=lambda: _get_int("VOLUME_LOOKBACK", 20))
    volume_multiplier: float = field(default_factory=lambda: _get_float("VOLUME_MULTIPLIER", 1.2))
    min_confidence_score: float = field(default_factory=lambda: _get_float("MIN_CONFIDENCE_SCORE", 80))

    weight_vwap: float = field(default_factory=lambda: _get_float("WEIGHT_VWAP", 20))
    weight_structure: float = field(default_factory=lambda: _get_float("WEIGHT_STRUCTURE", 25))
    weight_volume: float = field(default_factory=lambda: _get_float("WEIGHT_VOLUME", 20))
    weight_candlestick: float = field(default_factory=lambda: _get_float("WEIGHT_CANDLESTICK", 20))
    weight_trend: float = field(default_factory=lambda: _get_float("WEIGHT_TREND", 15))

    # Duplicate protection
    signal_cooldown_minutes: int = field(default_factory=lambda: _get_int("SIGNAL_COOLDOWN_MINUTES", 30))
    active_signals_file: str = field(default_factory=lambda: _get_str("ACTIVE_SIGNALS_FILE", "signals/active_signals.json"))

    # Sessions
    session_filter: str = field(default_factory=lambda: _get_str("SESSION_FILTER", "BOTH").upper())
    london_session_start: str = field(default_factory=lambda: _get_str("LONDON_SESSION_START", "07:00"))
    london_session_end: str = field(default_factory=lambda: _get_str("LONDON_SESSION_END", "16:00"))
    newyork_session_start: str = field(default_factory=lambda: _get_str("NEWYORK_SESSION_START", "12:00"))
    newyork_session_end: str = field(default_factory=lambda: _get_str("NEWYORK_SESSION_END", "21:00"))

    # Scanner
    scan_interval_seconds: int = field(default_factory=lambda: _get_int("SCAN_INTERVAL_SECONDS", 10))
    max_reconnect_attempts: int = field(default_factory=lambda: _get_int("MAX_RECONNECT_ATTEMPTS", 10))
    reconnect_backoff_seconds: int = field(default_factory=lambda: _get_int("RECONNECT_BACKOFF_SECONDS", 5))

    # Logging
    log_file: str = field(default_factory=lambda: _get_str("LOG_FILE", "logs/bot.log"))
    log_level: str = field(default_factory=lambda: _get_str("LOG_LEVEL", "INFO"))
    log_max_bytes: int = field(default_factory=lambda: _get_int("LOG_MAX_BYTES", 5 * 1024 * 1024))
    log_backup_count: int = field(default_factory=lambda: _get_int("LOG_BACKUP_COUNT", 5))

    # CSV history
    csv_history_file: str = field(default_factory=lambda: _get_str("CSV_HISTORY_FILE", "signals/signal_history.csv"))

    # Heartbeat / summary
    heartbeat_interval_hours: int = field(default_factory=lambda: _get_int("HEARTBEAT_INTERVAL_HOURS", 6))
    daily_summary_hour_utc: int = field(default_factory=lambda: _get_int("DAILY_SUMMARY_HOUR_UTC", 21))

    def weights_normalized(self) -> dict:
        """Return the confidence weights normalized so they sum to 100."""
        total = (
            self.weight_vwap
            + self.weight_structure
            + self.weight_volume
            + self.weight_candlestick
            + self.weight_trend
        )
        if total <= 0:
            raise ConfigError("Confidence weights must sum to a positive number.")
        scale = 100.0 / total
        return {
            "vwap": self.weight_vwap * scale,
            "structure": self.weight_structure * scale,
            "volume": self.weight_volume * scale,
            "candlestick": self.weight_candlestick * scale,
            "trend": self.weight_trend * scale,
        }


config = Config()
