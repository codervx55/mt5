"""
Thin wrapper around the MetaTrader5 Python package.

Handles connection, reconnection, and fetching OHLCV data as pandas
DataFrames. This module is the ONLY place that talks to the MT5 terminal
directly.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from config import config
from utils.logger import get_logger
from utils.retry import retry_with_backoff

logger = get_logger("mt5_client")

try:
    import MetaTrader5 as mt5
except ImportError:  # pragma: no cover - MetaTrader5 only installs on Windows
    mt5 = None
    logger.warning(
        "MetaTrader5 package not available on this platform. "
        "The bot must run on Windows with the MT5 terminal installed."
    )


TIMEFRAME_MAP = {
    "M1": "TIMEFRAME_M1",
    "M5": "TIMEFRAME_M5",
    "M15": "TIMEFRAME_M15",
    "M30": "TIMEFRAME_M30",
    "H1": "TIMEFRAME_H1",
    "H4": "TIMEFRAME_H4",
    "D1": "TIMEFRAME_D1",
}


class MT5ConnectionError(Exception):
    """Raised when MT5 cannot be initialized or connected."""


class MT5Client:
    def __init__(self) -> None:
        self._connected = False

    @retry_with_backoff(max_attempts=5, base_delay=3, exceptions=(MT5ConnectionError,))
    def connect(self) -> None:
        """Initialize the MT5 terminal connection (and log in if credentials are set)."""
        if mt5 is None:
            raise MT5ConnectionError("MetaTrader5 package is not installed on this platform.")

        kwargs = {}
        if config.mt5_terminal_path:
            kwargs["path"] = config.mt5_terminal_path

        initialized = mt5.initialize(**kwargs)
        if not initialized:
            raise MT5ConnectionError(f"mt5.initialize() failed: {mt5.last_error()}")

        if config.mt5_login and config.mt5_password and config.mt5_server:
            authorized = mt5.login(
                login=int(config.mt5_login),
                password=config.mt5_password,
                server=config.mt5_server,
            )
            if not authorized:
                raise MT5ConnectionError(f"mt5.login() failed: {mt5.last_error()}")

        self._connected = True
        logger.info("Connected to MT5 terminal successfully.")

    def ensure_connected(self) -> None:
        """Reconnect if the terminal connection has dropped."""
        if mt5 is None:
            raise MT5ConnectionError("MetaTrader5 package is not installed on this platform.")

        terminal_info = mt5.terminal_info()
        if terminal_info is None or not self._connected:
            logger.warning("MT5 connection lost. Reconnecting...")
            self._connected = False
            self.connect()

    def ensure_symbol(self, symbol: str) -> None:
        """Make sure a symbol is visible in Market Watch, raising if it does not exist."""
        info = mt5.symbol_info(symbol)
        if info is None:
            raise MT5ConnectionError(f"Symbol '{symbol}' not found on this broker/terminal.")
        if not info.visible:
            if not mt5.symbol_select(symbol, True):
                raise MT5ConnectionError(f"Could not enable symbol '{symbol}' in Market Watch.")

    def get_candles(self, symbol: str, timeframe: str, count: int = 300) -> pd.DataFrame:
        """
        Fetch the last `count` candles for `symbol`/`timeframe` as a
        DataFrame with columns: time, open, high, low, close, tick_volume.
        The most recent row may be a currently-forming candle; callers that
        need only CLOSED candles should drop the last row.
        """
        self.ensure_connected()
        self.ensure_symbol(symbol)

        tf_attr = TIMEFRAME_MAP.get(timeframe.upper())
        if tf_attr is None:
            raise ValueError(f"Unsupported timeframe: {timeframe}")
        tf_const = getattr(mt5, tf_attr)

        rates = mt5.copy_rates_from_pos(symbol, tf_const, 0, count)
        if rates is None or len(rates) == 0:
            raise MT5ConnectionError(f"No rate data returned for {symbol} {timeframe}: {mt5.last_error()}")

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        return df[["time", "open", "high", "low", "close", "tick_volume"]]

    def get_current_price(self, symbol: str) -> Optional[float]:
        self.ensure_connected()
        self.ensure_symbol(symbol)
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return None
        return float(tick.last or tick.bid)

    def shutdown(self) -> None:
        if mt5 is not None:
            mt5.shutdown()
        self._connected = False
        logger.info("MT5 connection closed.")


mt5_client = MT5Client()
