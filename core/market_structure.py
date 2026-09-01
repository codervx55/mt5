"""
Market structure detection: swing highs/lows, HH/HL/LH/LL classification,
Break of Structure (BOS) and Change of Character (CHoCH).

All detection works only on CLOSED candles - the last (currently forming)
candle in any dataframe passed in must already be excluded by the caller.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

import pandas as pd


class SwingType(str, Enum):
    HIGHER_HIGH = "HH"
    HIGHER_LOW = "HL"
    LOWER_HIGH = "LH"
    LOWER_LOW = "LL"


class StructureEvent(str, Enum):
    NONE = "none"
    BREAK_OF_STRUCTURE = "BOS"
    CHANGE_OF_CHARACTER = "CHoCH"


@dataclass
class Swing:
    index: int
    price: float
    kind: str  # "high" or "low"


@dataclass
class StructureResult:
    trend: str  # "bullish", "bearish", "ranging"
    last_swings: List[SwingType]
    event: StructureEvent
    swing_high: Optional[float]
    swing_low: Optional[float]


def _find_swings(df: pd.DataFrame, order: int = 2) -> List[Swing]:
    """
    Find local swing highs and lows using a simple fractal method: a bar is
    a swing high if it is the highest high within `order` bars on each side,
    and a swing low if it is the lowest low within `order` bars on each side.
    """
    swings: List[Swing] = []
    highs = df["high"].values
    lows = df["low"].values
    n = len(df)

    for i in range(order, n - order):
        window_highs = highs[i - order : i + order + 1]
        window_lows = lows[i - order : i + order + 1]

        is_swing_high = highs[i] == window_highs.max()
        is_swing_low = lows[i] == window_lows.min()

        if is_swing_high:
            swings.append(Swing(index=i, price=highs[i], kind="high"))
        if is_swing_low:
            swings.append(Swing(index=i, price=lows[i], kind="low"))

    return swings


def classify_structure(df: pd.DataFrame, order: int = 2) -> StructureResult:
    """
    Analyze the last portion of `df` (closed candles only) and classify
    the current market structure.
    """
    if len(df) < (order * 2) + 5:
        return StructureResult("ranging", [], StructureEvent.NONE, None, None)

    swings = _find_swings(df, order=order)
    highs = [s for s in swings if s.kind == "high"]
    lows = [s for s in swings if s.kind == "low"]

    if len(highs) < 2 or len(lows) < 2:
        return StructureResult("ranging", [], StructureEvent.NONE, None, None)

    last_swings: List[SwingType] = []

    if highs[-1].price > highs[-2].price:
        last_swings.append(SwingType.HIGHER_HIGH)
    else:
        last_swings.append(SwingType.LOWER_HIGH)

    if lows[-1].price > lows[-2].price:
        last_swings.append(SwingType.HIGHER_LOW)
    else:
        last_swings.append(SwingType.LOWER_LOW)

    is_bullish = SwingType.HIGHER_HIGH in last_swings and SwingType.HIGHER_LOW in last_swings
    is_bearish = SwingType.LOWER_HIGH in last_swings and SwingType.LOWER_LOW in last_swings

    trend = "bullish" if is_bullish else "bearish" if is_bearish else "ranging"

    # Detect BOS: price closes beyond the most recent opposite swing point
    # in the direction of the prevailing trend.
    last_close = df["close"].iloc[-1]
    event = StructureEvent.NONE

    if trend == "bullish" and last_close > highs[-2].price:
        event = StructureEvent.BREAK_OF_STRUCTURE
    elif trend == "bearish" and last_close < lows[-2].price:
        event = StructureEvent.BREAK_OF_STRUCTURE

    # CHoCH: price breaks structure in the OPPOSITE direction of the prior
    # trend, signalling a potential reversal.
    if trend == "bullish" and last_close < lows[-1].price:
        event = StructureEvent.CHANGE_OF_CHARACTER
    elif trend == "bearish" and last_close > highs[-1].price:
        event = StructureEvent.CHANGE_OF_CHARACTER

    return StructureResult(
        trend=trend,
        last_swings=last_swings,
        event=event,
        swing_high=highs[-1].price,
        swing_low=lows[-1].price,
    )


def structure_score(result: StructureResult, direction: str) -> float:
    """
    Score 0-100 describing how well the current structure supports a
    trade in `direction` ("buy" or "sell").
    """
    score = 0.0
    if direction == "buy" and result.trend == "bullish":
        score += 70.0
    elif direction == "sell" and result.trend == "bearish":
        score += 70.0

    if direction == "buy" and result.event == StructureEvent.BREAK_OF_STRUCTURE:
        score += 30.0
    elif direction == "sell" and result.event == StructureEvent.BREAK_OF_STRUCTURE:
        score += 30.0

    return min(score, 100.0)
