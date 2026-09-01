"""
Core signal generation engine.

Combines VWAP position, market structure, volume confirmation, candlestick
patterns, and higher-timeframe trend confirmation into a single weighted
confidence score. Only emits a `Signal` when every hard rule passes AND the
confidence score clears `config.min_confidence_score`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from config import config
from core import candlestick, market_structure, risk, volume, vwap
from core.market_structure import StructureEvent
from utils.logger import get_logger

logger = get_logger("signal_engine")


@dataclass
class Signal:
    symbol: str
    timeframe: str
    direction: str  # "buy" or "sell"
    entry: float
    stop_loss: float
    take_profit: float
    confidence: float
    rr_ratio: float
    reasons: list[str]


def _closed_candles(df: pd.DataFrame) -> pd.DataFrame:
    """Drop the last (currently forming) candle so all analysis uses closed bars only."""
    return df.iloc[:-1].reset_index(drop=True) if len(df) > 1 else df


def _evaluate_direction(df_closed: pd.DataFrame, direction: str) -> Optional[Signal]:
    weights = config.weights_normalized()
    reasons: list[str] = []
    score = 0.0

    # --- VWAP ---
    vwap_series = vwap.compute_vwap(df_closed)
    last_price = float(df_closed["close"].iloc[-1])
    last_vwap = float(vwap_series.iloc[-1]) if len(vwap_series) else float("nan")
    position = vwap.price_vs_vwap(last_price, last_vwap)
    pulled_back = vwap.is_pullback_to_vwap(df_closed, vwap_series)

    vwap_ok = (direction == "buy" and position == "above") or (direction == "sell" and position == "below")
    if not vwap_ok:
        return None
    score += weights["vwap"] * (1.0 if pulled_back else 0.6)
    reasons.append(f"Price {position} VWAP" + (" with pullback" if pulled_back else ""))

    # --- Market structure ---
    structure = market_structure.classify_structure(df_closed)
    structure_direction_ok = (direction == "buy" and structure.trend == "bullish") or (
        direction == "sell" and structure.trend == "bearish"
    )
    if not structure_direction_ok:
        return None
    struct_score = market_structure.structure_score(structure, direction)
    score += weights["structure"] * (struct_score / 100.0)
    reasons.append(f"Structure: {structure.trend}" + (f" ({structure.event.value})" if structure.event != StructureEvent.NONE else ""))

    # --- Volume ---
    vol_result = volume.check_volume_confirmation(df_closed)
    if not vol_result.confirmed:
        return None
    score += weights["volume"] * (volume.volume_score(vol_result) / 100.0)
    reasons.append(f"Volume {vol_result.ratio:.2f}x average")

    # --- Candlestick ---
    pattern = candlestick.best_pattern_for_direction(df_closed, direction)
    if pattern is None:
        return None
    score += weights["candlestick"] * (pattern.confidence / 100.0)
    reasons.append(f"Pattern: {pattern.name} ({pattern.confidence:.0f}%)")

    # --- Trend weight (reuses structure trend strength as a proxy) ---
    score += weights["trend"] * (struct_score / 100.0)

    confidence = round(min(score, 100.0), 2)
    if confidence < config.min_confidence_score:
        return None

    levels = risk.calculate_trade_levels(df_closed, direction)

    return Signal(
        symbol="",  # filled in by caller
        timeframe="",  # filled in by caller
        direction=direction,
        entry=levels.entry,
        stop_loss=levels.stop_loss,
        take_profit=levels.take_profit,
        confidence=confidence,
        rr_ratio=levels.rr_ratio,
        reasons=reasons,
    )


def generate_signal(
    symbol: str,
    timeframe: str,
    df: pd.DataFrame,
    confirmation_df: Optional[pd.DataFrame] = None,
) -> Optional[Signal]:
    """
    Evaluate BUY and SELL rules for `symbol`/`timeframe`. If `confirmation_df`
    (higher timeframe data) is provided, the signal's direction must also be
    supported by that timeframe's trend (multi-timeframe confirmation).
    """
    df_closed = _closed_candles(df)
    if len(df_closed) < 30:
        logger.debug("Not enough closed candles for %s %s to evaluate.", symbol, timeframe)
        return None

    for direction in ("buy", "sell"):
        signal = _evaluate_direction(df_closed, direction)
        if signal is None:
            continue

        if confirmation_df is not None:
            confirm_closed = _closed_candles(confirmation_df)
            if len(confirm_closed) >= 30:
                confirm_structure = market_structure.classify_structure(confirm_closed)
                confirm_ok = (direction == "buy" and confirm_structure.trend == "bullish") or (
                    direction == "sell" and confirm_structure.trend == "bearish"
                )
                if not confirm_ok:
                    logger.debug(
                        "%s %s %s signal rejected: higher timeframe trend is %s.",
                        symbol, timeframe, direction, confirm_structure.trend,
                    )
                    continue
                signal.reasons.append(f"Confirmed by {config.confirmation_timeframe} trend")

        signal.symbol = symbol
        signal.timeframe = timeframe
        return signal

    return None
