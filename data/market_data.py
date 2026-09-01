"""
Thin wrapper around the TwelveData REST API.

Replaces the old MT5-terminal dependency so this bot can run anywhere
(Railway, a VPS, GitHub Actions) instead of requiring a live MT5 terminal
open on a Windows machine 24/7.

Returns candles as pandas DataFrames with the exact same shape the old
MT5 client used: columns time, open, high, low, close, tick_volume. That
means core/* (candlestick, market_structure, risk, volume, vwap,
signal_engine) needed ZERO changes -- they only ever depended on that
DataFrame contract, never on MT5 itself.

Tradeoff vs MT5: prices come from TwelveData's aggregated feed, not your
specific broker's live quotes -- entries/spreads may differ slightly from
what you'd actually get executing the trade manually. Good enough for
signal generation; not a substitute for broker-accurate fills.
"""

from __future__ import annotations

import time
from typing import Optional

import pandas as pd
import requests

from config import config
from utils.logger import get_logger
from utils.retry import retry_with_backoff

logger = get_logger("market_data")

BASE_URL = "https://api.twelvedata.com"

# MT5-style symbol -> TwelveData symbol. Add more pairs here as needed.
SYMBOL_MAP = {
    "XAUUSD": "XAU/USD",
    "XAGUSD": "XAG/USD",
    "BTCUSD": "BTC/USD",
    "ETHUSD": "ETH/USD",
    "EURUSD": "EUR/USD",
    "GBPUSD": "GBP/USD",
    "USDJPY": "USD/JPY",
    "USDCHF": "USD/CHF",
    "AUDUSD": "AUD/USD",
    "NZDUSD": "NZD/USD",
    "USDCAD": "USD/CAD",
}

# MT5-style timeframe -> TwelveData interval
TIMEFRAME_MAP = {
    "M1": "1min",
    "M5": "5min",
    "M15": "15min",
    "M30": "30min",
    "H1": "1h",
    "H4": "4h",
    "D1": "1day",
}


class MarketDataError(Exception):
    """Raised when candle data cannot be fetched or parsed."""


def _map_symbol(symbol: str) -> str:
    mapped = SYMBOL_MAP.get(symbol.upper())
    if mapped is not None:
        return mapped
    # Fallback so an unmapped 6-letter pair like "EURJPY" still resolves to
    # "EUR/JPY" without a code change -- explicit entries above are still
    # preferred since they cover crypto/metals that don't follow this pattern.
    s = symbol.upper()
    guess = f"{s[:-3]}/{s[-3:]}" if len(s) >= 6 else s
    logger.warning("No explicit TwelveData mapping for '%s', guessing '%s'.", symbol, guess)
    return guess


class MarketDataClient:
    """Fetches candles from TwelveData with a short in-memory cache so the
    same symbol/timeframe isn't re-fetched twice in one scan cycle (e.g. once
    as an entry timeframe, again as another pair's confirmation timeframe).
    This matters because TwelveData's free tier has a tight per-minute
    request cap -- see README for sizing SCAN_INTERVAL_SECONDS against your
    SYMBOLS x TIMEFRAMES combo count."""

    def __init__(self) -> None:
        self._cache: dict[tuple[str, str], tuple[float, pd.DataFrame]] = {}
        self._cache_ttl_seconds = 30  # candles don't meaningfully change faster than this

    @retry_with_backoff(max_attempts=4, base_delay=3, exceptions=(MarketDataError, requests.RequestException))
    def get_candles(self, symbol: str, timeframe: str, count: int = 300) -> pd.DataFrame:
        """
        Fetch the last `count` candles for `symbol`/`timeframe` as a
        DataFrame with columns: time, open, high, low, close, tick_volume.
        Same contract the old MT5 client used. The most recent row may be a
        still-forming candle; callers needing only CLOSED candles should
        drop the last row (signal_engine.py already does this).
        """
        cache_key = (symbol.upper(), timeframe.upper())
        now = time.monotonic()
        cached = self._cache.get(cache_key)
        if cached and (now - cached[0]) < self._cache_ttl_seconds:
            return cached[1]

        td_symbol = _map_symbol(symbol)
        interval = TIMEFRAME_MAP.get(timeframe.upper())
        if interval is None:
            raise ValueError(f"Unsupported timeframe: {timeframe}")

        params = {
            "symbol": td_symbol,
            "interval": interval,
            "outputsize": count,
            "apikey": config.twelvedata_api_key,
            "format": "JSON",
            "order": "ASC",
        }
        response = requests.get(f"{BASE_URL}/time_series", params=params, timeout=30)
        data = response.json()

        if "values" not in data:
            raise MarketDataError(f"TwelveData error for {symbol} {timeframe}: {data}")

        rows = []
        for row in data["values"]:
            rows.append({
                "time": row["datetime"],
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "tick_volume": float(row.get("volume", 0) or 0),
            })

        df = pd.DataFrame(rows)
        df["time"] = pd.to_datetime(df["time"], utc=True)
        df = df[["time", "open", "high", "low", "close", "tick_volume"]]

        self._cache[cache_key] = (now, df)
        return df

    def get_current_price(self, symbol: str) -> Optional[float]:
        """Best-effort current price, derived from the latest closed candle
        on the shortest configured timeframe. Not a live tick like MT5 gave
        you -- accurate to within one candle's worth of lag."""
        try:
            df = self.get_candles(symbol, config.timeframes[0], count=2)
            return float(df["close"].iloc[-1])
        except Exception as exc:  # noqa: BLE001
            logger.error("Could not fetch current price for %s: %s", symbol, exc)
            return None

    def ping(self) -> bool:
        """Lightweight connectivity check used by /status and on startup."""
        try:
            self.get_candles(config.symbols[0], config.timeframes[0], count=2)
            return True
        except Exception:
            return False


market_data_client = MarketDataClient()
