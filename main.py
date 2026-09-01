"""
Entry point for the MT5 -> Telegram signal bot.

This bot NEVER places trades. It only scans MetaTrader 5 for
confluence-based setups and sends formatted alerts to Telegram for you to
execute manually.

Run with:
    python main.py
"""

from __future__ import annotations

import sys

from config import ConfigError
from scanner import Scanner
from utils.logger import get_logger

logger = get_logger("main")


def main() -> None:
    try:
        scanner = Scanner()
    except ConfigError as exc:
        logger.critical("Configuration error: %s", exc)
        sys.exit(1)

    try:
        scanner.start()
    except KeyboardInterrupt:
        logger.info("Shutdown requested by user (Ctrl+C).")
    except Exception as exc:  # noqa: BLE001
        logger.critical("Fatal error, bot is stopping: %s", exc)
    finally:
        scanner.stop()


if __name__ == "__main__":
    main()
