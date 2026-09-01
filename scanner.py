"""
The scanner: pulls fresh candles for every symbol/timeframe pair, runs the
signal engine, applies duplicate protection, and sends Telegram alerts for
new signals AND for signals that just hit TP/SL. Designed to never crash --
every iteration is wrapped so a single bad candle fetch or a transient
network blip does not kill the process/run.

Market data comes from TwelveData (see data/market_data.py) rather than a
live MT5 terminal.

Two ways to run this:
  - Continuous (Railway, a VPS): Scanner().start() loops forever, sleeping
    config.scan_interval_seconds between cycles, with a live Telegram
    command listener (/status, /pairs, etc).
  - Single-shot (GitHub Actions on a cron schedule): Scanner().run_once()
    does exactly one scan-all-pairs pass and returns. Heartbeat/daily-summary
    timers are persisted to disk (storage/scanner_state.py) so they still
    fire on schedule across separate runs. No command listener in this mode
    -- there's no long-lived process for it to poll from.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from config import config
from core import market_structure, sessions
from core.signal_engine import generate_signal
from data.market_data import MarketDataError, market_data_client
from storage import csv_logger, scanner_state
from storage.signal_store import ActiveSignal, signal_store
from telegram_bot import formatter
from telegram_bot.client import telegram_client
from telegram_bot.commands import CommandListener
from utils.logger import get_logger

logger = get_logger("scanner")


class Scanner:
    def __init__(self) -> None:
        self._running = False
        self._command_listener = CommandListener(data_connected_fn=self._is_data_feed_connected)

    def _is_data_feed_connected(self) -> bool:
        return market_data_client.ping()

    # ---- Continuous mode (Railway / VPS) ----

    def start(self) -> None:
        logger.info("Starting TwelveData -> Telegram signal bot (continuous mode).")
        if not market_data_client.ping():
            logger.warning("Initial TwelveData connectivity check failed -- check TWELVEDATA_API_KEY. Continuing anyway; will retry on each scan.")
        self._command_listener.start()
        telegram_client.broadcast("🚀 <b>Bot started</b> and scanning for signals.", admin_only=True)
        self._running = True
        self._loop()

    def stop(self) -> None:
        self._running = False
        self._command_listener.stop()
        logger.info("Scanner stopped.")

    def _loop(self) -> None:
        while self._running:
            self.run_once()
            time.sleep(config.scan_interval_seconds)

    # ---- Single-shot mode (GitHub Actions cron) ----

    def run_once(self) -> None:
        """Performs exactly one scan-all-pairs cycle, plus heartbeat/daily
        summary checks. Safe to call repeatedly from a scheduler instead of
        running start() as a long-lived loop."""
        try:
            self._scan_once()
            self._maybe_send_heartbeat()
            self._maybe_send_daily_summary()
        except MarketDataError as exc:
            logger.error("Market data error during scan: %s. Will retry next cycle.", exc)
        except Exception as exc:  # noqa: BLE001 - a scan cycle must never crash the process
            logger.exception("Unexpected error during scan cycle: %s", exc)

    def _scan_once(self) -> None:
        if not sessions.is_within_active_session():
            logger.info("Outside active trading session; skipping scan cycle.")
            return

        for symbol in config.symbols:
            for timeframe in config.timeframes:
                self._scan_symbol_timeframe(symbol, timeframe)

    def _scan_symbol_timeframe(self, symbol: str, timeframe: str) -> None:
        df = market_data_client.get_candles(symbol, timeframe, count=300)

        confirmation_df = None
        if config.confirmation_timeframe and config.confirmation_timeframe != timeframe:
            confirmation_df = market_data_client.get_candles(symbol, config.confirmation_timeframe, count=300)

        # Close out any active signal whose TP/SL has been hit, using the
        # latest price, and alert on it (this is the main thing single-shot
        # mode needs that the old continuous-only version didn't bother
        # with -- each run is a fresh process, so a hit has to be announced
        # the moment this run notices it).
        current_price = float(df["close"].iloc[-1])
        for direction in ("buy", "sell"):
            closed = signal_store.clear_if_hit(symbol, timeframe, direction, current_price)
            if closed is not None:
                telegram_client.broadcast(formatter.format_close_message(closed))
                logger.info("Closed signal #%03d: %s %s %s (%s @ %s)",
                            closed["signal_number"], symbol, timeframe, direction,
                            closed["close_reason"], closed["close_price"])

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
        telegram_client.broadcast(message)
        logger.info("Sent signal #%03d: %s %s %s @ %s", signal_number, symbol, timeframe, signal.direction, signal.entry)

    def _maybe_send_heartbeat(self) -> None:
        state = scanner_state.load()
        now = datetime.now(timezone.utc)
        last_heartbeat = datetime.fromisoformat(state.last_heartbeat)
        if now - last_heartbeat >= timedelta(hours=config.heartbeat_interval_hours):
            telegram_client.broadcast(formatter.format_heartbeat_message(), admin_only=True)
            state.last_heartbeat = now.isoformat()
            scanner_state.save(state)

    def _maybe_send_daily_summary(self) -> None:
        state = scanner_state.load()
        now = datetime.now(timezone.utc)
        today_str = now.strftime("%Y-%m-%d")
        if now.hour == config.daily_summary_hour_utc and state.last_summary_date != today_str:
            rows = csv_logger.read_today_signals()
            telegram_client.broadcast(formatter.format_daily_summary(rows), admin_only=True)
            state.last_summary_date = today_str
            scanner_state.save(state)