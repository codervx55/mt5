"""
Candlestick pattern recognition.

Each detector inspects the last one or two CLOSED candles of a dataframe
and returns a `PatternMatch` with a confidence score (0-100). Only closed
candles should ever be passed in - the caller is responsible for excluding
the currently-forming bar.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd


@dataclass
class PatternMatch:
    name: str
    direction: str  # "buy" or "sell"
    confidence: float  # 0-100


def _body(row: pd.Series) -> float:
    return abs(row["close"] - row["open"])


def _range(row: pd.Series) -> float:
    return max(row["high"] - row["low"], 1e-12)


def _upper_wick(row: pd.Series) -> float:
    return row["high"] - max(row["close"], row["open"])


def _lower_wick(row: pd.Series) -> float:
    return min(row["close"], row["open"]) - row["low"]


def detect_bullish_engulfing(df: pd.DataFrame) -> Optional[PatternMatch]:
    if len(df) < 2:
        return None
    prev, curr = df.iloc[-2], df.iloc[-1]
    prev_bearish = prev["close"] < prev["open"]
    curr_bullish = curr["close"] > curr["open"]
    engulfs = curr["close"] >= prev["open"] and curr["open"] <= prev["close"]
    if prev_bearish and curr_bullish and engulfs:
        size_ratio = _body(curr) / max(_body(prev), 1e-12)
        confidence = min(60 + size_ratio * 15, 100)
        return PatternMatch("Bullish Engulfing", "buy", confidence)
    return None


def detect_bearish_engulfing(df: pd.DataFrame) -> Optional[PatternMatch]:
    if len(df) < 2:
        return None
    prev, curr = df.iloc[-2], df.iloc[-1]
    prev_bullish = prev["close"] > prev["open"]
    curr_bearish = curr["close"] < curr["open"]
    engulfs = curr["close"] <= prev["open"] and curr["open"] >= prev["close"]
    if prev_bullish and curr_bearish and engulfs:
        size_ratio = _body(curr) / max(_body(prev), 1e-12)
        confidence = min(60 + size_ratio * 15, 100)
        return PatternMatch("Bearish Engulfing", "sell", confidence)
    return None


def detect_hammer(df: pd.DataFrame) -> Optional[PatternMatch]:
    if len(df) < 1:
        return None
    row = df.iloc[-1]
    body = _body(row)
    rng = _range(row)
    lower_wick = _lower_wick(row)
    upper_wick = _upper_wick(row)

    if lower_wick >= body * 2 and upper_wick <= body * 0.5 and body / rng < 0.4:
        confidence = min(50 + (lower_wick / rng) * 50, 100)
        return PatternMatch("Hammer", "buy", confidence)
    return None


def detect_shooting_star(df: pd.DataFrame) -> Optional[PatternMatch]:
    if len(df) < 1:
        return None
    row = df.iloc[-1]
    body = _body(row)
    rng = _range(row)
    lower_wick = _lower_wick(row)
    upper_wick = _upper_wick(row)

    if upper_wick >= body * 2 and lower_wick <= body * 0.5 and body / rng < 0.4:
        confidence = min(50 + (upper_wick / rng) * 50, 100)
        return PatternMatch("Shooting Star", "sell", confidence)
    return None


def detect_rejection_candle(df: pd.DataFrame) -> Optional[PatternMatch]:
    """
    A strong rejection candle: a long wick on one side with a small body,
    signalling price was pushed back sharply. Distinct from hammer /
    shooting star in that it does not require a small body-to-range ratio
    threshold as strict, and works on either bullish or bearish closes.
    """
    if len(df) < 1:
        return None
    row = df.iloc[-1]
    rng = _range(row)
    lower_wick = _lower_wick(row)
    upper_wick = _upper_wick(row)

    if lower_wick / rng >= 0.6:
        return PatternMatch("Strong Rejection (bullish)", "buy", min(50 + (lower_wick / rng) * 50, 100))
    if upper_wick / rng >= 0.6:
        return PatternMatch("Strong Rejection (bearish)", "sell", min(50 + (upper_wick / rng) * 50, 100))
    return None


def best_pattern_for_direction(df: pd.DataFrame, direction: str) -> Optional[PatternMatch]:
    """Run all detectors and return the highest-confidence match matching `direction`."""
    detectors = [
        detect_bullish_engulfing,
        detect_bearish_engulfing,
        detect_hammer,
        detect_shooting_star,
        detect_rejection_candle,
    ]
    matches = [d(df) for d in detectors]
    matches = [m for m in matches if m is not None and m.direction == direction]
    if not matches:
        return None
    return max(matches, key=lambda m: m.confidence)
