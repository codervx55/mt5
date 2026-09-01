"""CSV history logging for every signal sent."""

from __future__ import annotations

import csv
import os
import threading
from datetime import datetime, timezone

from config import config

_lock = threading.Lock()

_COLUMNS = [
    "date",
    "time",
    "pair",
    "timeframe",
    "entry",
    "sl",
    "tp",
    "confidence",
    "direction",
    "signal_number",
    "result",
]


def _ensure_file() -> None:
    path = config.csv_history_file
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    if not os.path.exists(path):
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=_COLUMNS)
            writer.writeheader()


def log_signal(
    pair: str,
    timeframe: str,
    entry: float,
    stop_loss: float,
    take_profit: float,
    confidence: float,
    direction: str,
    signal_number: int,
) -> None:
    """Append a new row to the CSV signal history. `result` is left blank."""
    with _lock:
        _ensure_file()
        now = datetime.now(timezone.utc)
        with open(config.csv_history_file, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=_COLUMNS)
            writer.writerow(
                {
                    "date": now.strftime("%Y-%m-%d"),
                    "time": now.strftime("%H:%M:%S"),
                    "pair": pair,
                    "timeframe": timeframe,
                    "entry": entry,
                    "sl": stop_loss,
                    "tp": take_profit,
                    "confidence": confidence,
                    "direction": direction.upper(),
                    "signal_number": signal_number,
                    "result": "",
                }
            )


def read_today_signals() -> list[dict]:
    """Return all rows logged today (UTC)."""
    _ensure_file()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    rows = []
    with open(config.csv_history_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["date"] == today:
                rows.append(row)
    return rows


def read_last_signal() -> dict | None:
    """Return the most recently logged signal row, or None if history is empty."""
    _ensure_file()
    with open(config.csv_history_file, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return rows[-1] if rows else None
