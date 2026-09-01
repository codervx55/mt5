"""Trading session filters (London / New York), evaluated in UTC."""

from __future__ import annotations

from datetime import datetime, time as dtime

from config import config


def _parse_hhmm(value: str) -> dtime:
    hour, minute = value.split(":")
    return dtime(int(hour), int(minute))


def _in_range(now: dtime, start: dtime, end: dtime) -> bool:
    if start <= end:
        return start <= now <= end
    # Overnight session (wraps past midnight UTC).
    return now >= start or now <= end


def is_within_active_session(now_utc: datetime | None = None) -> bool:
    """Return True if the current UTC time falls within the configured session filter."""
    mode = config.session_filter.upper()
    if mode == "OFF":
        return True

    now_utc = now_utc or datetime.utcnow()
    now_time = now_utc.time()

    london = _in_range(now_time, _parse_hhmm(config.london_session_start), _parse_hhmm(config.london_session_end))
    newyork = _in_range(now_time, _parse_hhmm(config.newyork_session_start), _parse_hhmm(config.newyork_session_end))

    if mode == "LONDON":
        return london
    if mode == "NEWYORK":
        return newyork
    if mode == "BOTH":
        return london or newyork
    return True
