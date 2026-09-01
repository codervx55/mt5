"""
Manual VWAP (Volume Weighted Average Price) implementation.

VWAP = sum(typical_price * volume) / sum(volume)

We deliberately do not rely on any MT5 built-in indicator - VWAP is
computed directly from OHLCV data using the typical price
(high + low + close) / 3, session-anchored (resets every UTC day).
"""

from __future__ import annotations

import pandas as pd


def compute_vwap(df: pd.DataFrame, anchor_daily: bool = True) -> pd.Series:
    """
    Compute VWAP for a DataFrame with columns: high, low, close, tick_volume, time.

    Args:
        df: OHLCV dataframe sorted ascending by time, with a `time`
            column of pandas Timestamps (UTC).
        anchor_daily: if True, VWAP resets at the start of each UTC day
            (standard intraday VWAP behaviour). If False, VWAP accumulates
            over the whole dataframe.

    Returns:
        A pandas Series of VWAP values aligned with df's index.
    """
    if df.empty:
        return pd.Series(dtype=float)

    typical_price = (df["high"] + df["low"] + df["close"]) / 3.0
    pv = typical_price * df["tick_volume"]

    if anchor_daily:
        day_key = df["time"].dt.floor("D")
        cum_pv = pv.groupby(day_key).cumsum()
        cum_vol = df["tick_volume"].groupby(day_key).cumsum()
    else:
        cum_pv = pv.cumsum()
        cum_vol = df["tick_volume"].cumsum()

    vwap = cum_pv / cum_vol.replace(0, pd.NA)
    return vwap.astype(float)


def price_vs_vwap(price: float, vwap_value: float) -> str:
    """Return 'above', 'below', or 'at' describing price relative to VWAP."""
    if pd.isna(vwap_value):
        return "at"
    if price > vwap_value:
        return "above"
    if price < vwap_value:
        return "below"
    return "at"


def is_pullback_to_vwap(df: pd.DataFrame, vwap: pd.Series, lookback: int = 5, tolerance_pct: float = 0.15) -> bool:
    """
    Detect whether price recently pulled back toward the VWAP line within
    the last `lookback` candles (distance from VWAP within tolerance_pct%).
    """
    if len(df) < lookback or vwap.empty:
        return False

    recent_close = df["close"].iloc[-lookback:]
    recent_vwap = vwap.iloc[-lookback:]
    distance_pct = ((recent_close - recent_vwap).abs() / recent_vwap.replace(0, pd.NA)) * 100
    return bool((distance_pct <= tolerance_pct).any())
