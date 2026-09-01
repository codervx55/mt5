"""
The continuous scanner loop.

Runs forever: pulls fresh candles for every symbol/timeframe pair, runs the
signal engine, applies duplicate protection, and sends Telegram alerts.
Also drives the heartbeat and daily-summary timers. Designed to never
crash - every iteration is wrapped so a single bad candle fetch or a
transient network blip does not kill the process.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from config import config
from core import market_structure, sessions
from core.signal_engine import generate_signal
from data.mt5_client import MT5ConnectionError, mt5_client
from storage import csv_logger
from storage.signal_store import ActiveSignal, signal_store
from telegram_bot import formatter
from telegram_bot.client import telegram_client
from telegram_bot.commands import CommandListener
from utils.logger import get_logger

logger = get_logger("scanner")


class Scanner:
    def __init__(self) -> None:
        self._running = False
        self._last_heartbeat = datetime.now(timezone.utc)
        self._last_summary_date: str | None = None
        self._reconnect_attempts = 0
        self._command_listener = CommandListener(mt5_connected_fn=self._is_mt5_connected)

    def _is_mt5_connected(self) -> bool:
        try:
            mt5_client.ensure_connected()
            return True
        except MT5ConnectionError:
            return False

    def start(self) -> None:
        logger.info("Starting MT5 -> Telegram signal bot.")
        self._connect_with_retries()
        self._command_listener.start()
        telegram_client.send_message("🚀 <b>Bot started</b> and scanning for signals.")
        self._running = True
        self._loop()

    def stop(self) -> None:
        self._running = False
        self._command_listener.stop()
        mt5_client.shutdown()
        logger.info("Scanner stopped.")

    def _connect_with_retries(self) -> None:
        while True:
            try:
                mt5_client.connect()
                self._reconnect_attempts = 0
                return
            except MT5ConnectionError as exc:
                self._reconnect_attempts += 1
                if self._reconnect_attempts > config.max_reconnect_attempts:
                    logger.critical("Exceeded max reconnect attempts (%s). Exiting.", config.max_reconnect_attempts)
                    raise
                delay = config.reconnect_backoff_seconds * self._reconnect_attempts
                logger.warning("MT5 connect failed (%s). Retrying in %ss...", exc, delay)
                time.sleep(delay)

    def _loop(self) -> None:
        while self._running:
            try:
                self._scan_once()
                self._maybe_send_heartbeat()
                self._maybe_send_daily_summary()
            except MT5ConnectionError as exc:
                logger.error("MT5 connection error during scan: %s. Reconnecting...", exc)
                self._connect_with_retries()
            except Exception as exc:  # noqa: BLE001 - the scanner must never crash
                logger.exception("Unexpected error during scan cycle: %s", exc)

            time.sleep(config.scan_interval_seconds)

    def _scan_once(self) -> None:
        if not sessions.is_within_active_session():
            logger.debug("Outside active trading session; skipping scan cycle.")
            return

        for symbol in config.symbols:
            for timeframe in config.timeframes:
                self._scan_symbol_timeframe(symbol, timeframe)

    def _scan_symbol_timeframe(self, symbol: str, timeframe: str) -> None:
        df = mt5_client.get_candles(symbol, timeframe, count=300)

        confirmation_df = None
        if config.confirmation_timeframe and config.confirmation_timeframe != timeframe:
            confirmation_df = mt5_client.get_candles(symbol, config.confirmation_timeframe, count=300)

        # Clear any active signal whose TP/SL has been hit, using the latest price.
        current_price = float(df["close"].iloc[-1])
        for direction in ("buy", "sell"):
            signal_store.clear_if_hit(symbol, timeframe, direction, current_price)

        structure = market_structure.classify_structure(df.iloc[:-1] if len(df) > 1 else df)
        signal_store.clear_on_structure_change(symbol, timeframe, structure.trend)

        signal = generate_signal(symbol, timeframe, df, confirmation_df=confirmation_df)
        if signal is None:
            return

        if not signal_store.can_emit(symbol, timeframe, signal.direction):
            logger.debug("Signal for %s %s %s suppressed (cooldown/active).", symbol, timeframe, signal.direction)
            return

        signal_number = signal_store.next_signal_number()
        signal_store.register(
            ActiveSignal(
                symbol=symbol,
                timeframe=timeframe,
                direction=signal.direction,
                entry=signal.entry,
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit,
                confidence=signal.confidence,
                signal_number=signal_number,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
        )

        csv_logger.log_signal(
            pair=symbol,
            timeframe=timeframe,
            entry=signal.entry,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            confidence=signal.confidence,
            direction=signal.direction,
            signal_number=signal_number,
        )

        message = formatter.format_signal_message(signal, signal_number)
        telegram_client.send_message(message)
        logger.info("Sent signal #%03d: %s %s %s @ %s", signal_number, symbol, timeframe, signal.direction, signal.entry)

    def _maybe_send_heartbeat(self) -> None:
        now = datetime.now(timezone.utc)
        if now - self._last_heartbeat >= timedelta(hours=config.heartbeat_interval_hours):
            telegram_client.send_message(formatter.format_heartbeat_message())
            self._last_heartbeat = now

    def _maybe_send_daily_summary(self) -> None:
        now = datetime.now(timezone.utc)
        today_str = now.strftime("%Y-%m-%d")
        if now.hour == config.daily_summary_hour_utc and self._last_summary_date != today_str:
            rows = csv_logger.read_today_signals()
            telegram_client.send_message(formatter.format_daily_summary(rows))
            self._last_summary_date = today_str
