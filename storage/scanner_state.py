"""
Tiny persisted state for the scanner's timers (last heartbeat sent, last
daily-summary date). In continuous mode (Railway/VPS) these would happily
live as in-memory attributes on the Scanner instance for its whole
lifetime. But in single-shot mode (GitHub Actions, one fresh process per
scheduled run) they need to survive between runs, so they're persisted to
a small JSON file next to the other signal state.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Optional

from config import config
from utils.logger import get_logger

logger = get_logger("scanner_state")


@dataclass
class TimerState:
    last_heartbeat: str  # ISO 8601 UTC
    last_summary_date: Optional[str]  # "YYYY-MM-DD" or None


def _path() -> str:
    signals_dir = os.path.dirname(config.active_signals_file) or "."
    return os.path.join(signals_dir, "scanner_state.json")


def load() -> TimerState:
    path = _path()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return TimerState(
                last_heartbeat=data.get("last_heartbeat", datetime.now(timezone.utc).isoformat()),
                last_summary_date=data.get("last_summary_date"),
            )
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Could not read %s (%s); starting fresh.", path, exc)

    return TimerState(last_heartbeat=datetime.now(timezone.utc).isoformat(), last_summary_date=None)


def save(state: TimerState) -> None:
    path = _path()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(asdict(state), f, indent=2)
    os.replace(tmp_path, path)
