"""
Duplicate signal protection.

Tracks active signals per (symbol, timeframe, direction) key in a JSON
file. A new signal for the same key is blocked until one of:
  - TP hit
  - SL hit
  - Structure changes (direction flips)
  - Cooldown period expires

This makes the store resilient to bot restarts since state is persisted
to disk.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from config import config
from utils.logger import get_logger

logger = get_logger("signal_store")

_lock = threading.Lock()


@dataclass
class ActiveSignal:
    symbol: str
    timeframe: str
    direction: str
    entry: float
    stop_loss: float
    take_profit: float
    confidence: float
    signal_number: int
    created_at: str  # ISO 8601 UTC


class SignalStore:
    def __init__(self, path: str | None = None) -> None:
        self.path = path or config.active_signals_file
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        self._data: Dict[str, dict] = self._load()
        self._counter_path = os.path.join(os.path.dirname(self.path) or ".", "signal_counter.json")
        self._counter = self._load_counter()

    def _load(self) -> Dict[str, dict]:
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Could not read %s (%s); starting with empty store.", self.path, exc)
        return {}

    def _save(self) -> None:
        tmp_path = f"{self.path}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2)
        os.replace(tmp_path, self.path)

    def _load_counter(self) -> int:
        if os.path.exists(self._counter_path):
            try:
                with open(self._counter_path, "r", encoding="utf-8") as f:
                    return json.load(f).get("count", 0)
            except (json.JSONDecodeError, OSError):
                return 0
        return 0

    def _save_counter(self) -> None:
        with open(self._counter_path, "w", encoding="utf-8") as f:
            json.dump({"count": self._counter}, f)

    @staticmethod
    def _key(symbol: str, timeframe: str, direction: str) -> str:
        return f"{symbol}:{timeframe}:{direction}"

    def next_signal_number(self) -> int:
        with _lock:
            self._counter += 1
            self._save_counter()
            return self._counter

    def can_emit(self, symbol: str, timeframe: str, direction: str) -> bool:
        """Return True if a new signal for this key is allowed right now."""
        with _lock:
            key = self._key(symbol, timeframe, direction)
            existing = self._data.get(key)
            if existing is None:
                return True

            created_at = datetime.fromisoformat(existing["created_at"])
            cooldown_expired = datetime.now(timezone.utc) >= created_at + timedelta(
                minutes=config.signal_cooldown_minutes
            )
            if cooldown_expired:
                logger.info("Cooldown expired for %s; allowing new signal.", key)
                del self._data[key]
                self._save()
                return True

            return False

    def register(self, signal: ActiveSignal) -> None:
        with _lock:
            key = self._key(signal.symbol, signal.timeframe, signal.direction)
            self._data[key] = asdict(signal)
            self._save()

    def get_active(self, symbol: str, timeframe: str, direction: str) -> Optional[dict]:
        return self._data.get(self._key(symbol, timeframe, direction))

    def get_all_active(self) -> Dict[str, dict]:
        with _lock:
            return dict(self._data)

    def clear_if_hit(self, symbol: str, timeframe: str, direction: str, current_price: float) -> None:
        """
        Remove the active signal if price has hit its TP or SL. Should be
        called periodically by the scanner for every open (symbol, timeframe,
        direction) combination.
        """
        with _lock:
            key = self._key(symbol, timeframe, direction)
            existing = self._data.get(key)
            if existing is None:
                return

            hit = False
            if direction == "buy":
                if current_price >= existing["take_profit"] or current_price <= existing["stop_loss"]:
                    hit = True
            else:
                if current_price <= existing["take_profit"] or current_price >= existing["stop_loss"]:
                    hit = True

            if hit:
                logger.info("Signal %s hit TP/SL; clearing from active store.", key)
                del self._data[key]
                self._save()

    def clear_on_structure_change(self, symbol: str, timeframe: str, new_trend: str) -> None:
        """Clear an opposing-direction active signal if the market structure has flipped."""
        with _lock:
            opposite_direction = "sell" if new_trend == "bullish" else "buy" if new_trend == "bearish" else None
            if opposite_direction is None:
                return
            key = self._key(symbol, timeframe, opposite_direction)
            if key in self._data:
                logger.info("Structure changed to %s; clearing stale %s signal.", new_trend, key)
                del self._data[key]
                self._save()


signal_store = SignalStore()
