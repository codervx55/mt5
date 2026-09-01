"""Entry / Stop Loss / Take Profit calculation using a fixed risk-reward ratio."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from config import config


@dataclass
class TradeLevels:
    entry: float
    stop_loss: float
    take_profit: float
    risk: float
    reward: float
    rr_ratio: float


def _swing_based_stop(df: pd.DataFrame, direction: str, buffer_atr_mult: float = 0.25) -> float:
    """
    Derive a stop-loss level from the most recent swing low (buy) or swing
    high (sell), with a small ATR-based buffer beyond it.
    """
    atr = _average_true_range(df)
    lookback = df.iloc[-10:]

    if direction == "buy":
        swing_low = lookback["low"].min()
        return swing_low - (atr * buffer_atr_mult)
    else:
        swing_high = lookback["high"].max()
        return swing_high + (atr * buffer_atr_mult)


def _average_true_range(df: pd.DataFrame, period: int = 14) -> float:
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = true_range.rolling(window=period, min_periods=1).mean().iloc[-1]
    return float(atr) if pd.notna(atr) else float(high_low.iloc[-1])


def calculate_trade_levels(df: pd.DataFrame, direction: str, rr_ratio: float | None = None) -> TradeLevels:
    """
    Calculate Entry, Stop Loss, and Take Profit for a trade.

    Entry: last closed candle's close price.
    Stop Loss: swing-based, beyond the most recent relevant swing point.
    Take Profit: Entry + (Risk * rr_ratio) for buys, Entry - (Risk * rr_ratio) for sells.
    """
    rr_ratio = rr_ratio if rr_ratio is not None else config.risk_reward_ratio
    entry = float(df["close"].iloc[-1])
    stop_loss = _swing_based_stop(df, direction)

    if direction == "buy":
        risk = entry - stop_loss
        if risk <= 0:
            risk = _average_true_range(df)
            stop_loss = entry - risk
        take_profit = entry + (risk * rr_ratio)
    else:
        risk = stop_loss - entry
        if risk <= 0:
            risk = _average_true_range(df)
            stop_loss = entry + risk
        take_profit = entry - (risk * rr_ratio)

    reward = abs(take_profit - entry)
    actual_rr = reward / risk if risk > 0 else 0.0

    return TradeLevels(
        entry=round(entry, 5),
        stop_loss=round(stop_loss, 5),
        take_profit=round(take_profit, 5),
        risk=round(risk, 5),
        reward=round(reward, 5),
        rr_ratio=round(actual_rr, 2),
    )
