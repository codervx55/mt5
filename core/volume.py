"""Volume confirmation using MT5 tick volume compared to a rolling average."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from config import config


@dataclass
class VolumeResult:
    current_volume: float
    average_volume: float
    ratio: float
    confirmed: bool


def check_volume_confirmation(df: pd.DataFrame, lookback: int | None = None, multiplier: float | None = None) -> VolumeResult:
    """
    Compare the last CLOSED candle's tick_volume against the average of the
    previous `lookback` candles. Confirmed when:

        current_volume > average_volume * multiplier
    """
    lookback = lookback or config.volume_lookback
    multiplier = multiplier if multiplier is not None else config.volume_multiplier

    if len(df) < lookback + 1:
        return VolumeResult(0.0, 0.0, 0.0, False)

    current_volume = float(df["tick_volume"].iloc[-1])
    average_volume = float(df["tick_volume"].iloc[-(lookback + 1) : -1].mean())

    ratio = current_volume / average_volume if average_volume > 0 else 0.0
    confirmed = current_volume > (average_volume * multiplier)

    return VolumeResult(current_volume, average_volume, ratio, confirmed)


def volume_score(result: VolumeResult) -> float:
    """Score 0-100: scales with how far volume exceeds the required multiplier."""
    if not result.confirmed:
        return 0.0
    # Cap the bonus contribution at 2x the required ratio.
    excess = min(result.ratio, config.volume_multiplier * 2)
    return min(100.0, (excess / config.volume_multiplier) * 50)
