"""
Entry point for the MT5-style -> Telegram signal bot.

This bot NEVER places trades. It only scans market data (via TwelveData,
see data/market_data.py) for confluence-based setups and sends formatted
alerts to Telegram for you to execute manually.

Run with:
    python main.py            # continuous mode (Railway, a VPS)
    python main.py --once     # single scan-all-pairs cycle then exit
                               # (for GitHub Actions / cron scheduling)
"""

from __future__ import annotations

import argparse
import sys

from config import ConfigError
from scanner import Scanner
from utils.logger import get_logger

logger = get_logger("main")


def main() -> None:
    parser = argparse.ArgumentParser(description="TwelveData -> Telegram signal bot")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single scan-all-pairs cycle and exit (for GitHub Actions/cron scheduling).",
    )
    args = parser.parse_args()

    try:
        scanner = Scanner()
    except ConfigError as exc:
        logger.critical("Configuration error: %s", exc)
        sys.exit(1)

    if args.once:
        scanner.run_once()
        return

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
