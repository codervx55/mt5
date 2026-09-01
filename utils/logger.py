"""Rotating file + console logger shared by every module."""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler

from config import config

_LOGGER_NAME = "mt5_signal_bot"
_configured = False


def get_logger(name: str = _LOGGER_NAME) -> logging.Logger:
    """Return a configured logger. Safe to call repeatedly from any module."""
    global _configured

    root_logger = logging.getLogger(_LOGGER_NAME)

    if not _configured:
        os.makedirs(os.path.dirname(config.log_file) or ".", exist_ok=True)

        root_logger.setLevel(getattr(logging, config.log_level.upper(), logging.INFO))

        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        file_handler = RotatingFileHandler(
            config.log_file,
            maxBytes=config.log_max_bytes,
            backupCount=config.log_backup_count,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)

        root_logger.addHandler(file_handler)
        root_logger.addHandler(console_handler)
        root_logger.propagate = False

        _configured = True

    if name == _LOGGER_NAME:
        return root_logger
    return root_logger.getChild(name)
