from __future__ import annotations

import logging
import logging.config
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_CONFIGURED = False


def _resolve_log_dir() -> Path:
    configured = os.getenv("AETHOS_LOG_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path.cwd() / "logs"


class ColorFormatter(logging.Formatter):
    _RESET = "\x1b[0m"
    _LEVEL_COLORS = {
        logging.DEBUG: "\x1b[36m",      # cyan
        logging.INFO: "\x1b[32m",       # green
        logging.WARNING: "\x1b[33m",    # yellow
        logging.ERROR: "\x1b[31m",      # red
        logging.CRITICAL: "\x1b[1;35m", # bold magenta
    }

    def format(self, record: logging.LogRecord) -> str:
        original = record.levelname
        color = self._LEVEL_COLORS.get(record.levelno, "")
        if color:
            record.levelname = f"{color}{record.levelname}{self._RESET}"
        try:
            return super().format(record)
        finally:
            record.levelname = original


def _should_use_color() -> bool:
    mode = os.getenv("AETHOS_LOG_COLOR", "auto").strip().lower()
    if mode == "never" or os.getenv("NO_COLOR"):
        return False
    if mode == "always":
        return True
    # auto
    return bool(sys.stderr and hasattr(sys.stderr, "isatty") and sys.stderr.isatty())


def setup_logging() -> None:
    """Configure project-wide logging once."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    log_level = os.getenv("AETHOS_LOG_LEVEL", "INFO").upper()
    log_dir = _resolve_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)

    app_log = str(log_dir / "app.log")
    error_log = str(log_dir / "error.log")

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "standard": {
                    "format": "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                    "datefmt": "%Y-%m-%d %H:%M:%S",
                },
                "detailed": {
                    "format": "%(asctime)s | %(levelname)-8s | %(name)s | %(filename)s:%(lineno)d | %(message)s",
                    "datefmt": "%Y-%m-%d %H:%M:%S",
                },
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "level": log_level,
                    "formatter": "standard",
                },
                "app_file": {
                    "class": "logging.handlers.RotatingFileHandler",
                    "level": log_level,
                    "formatter": "detailed",
                    "filename": app_log,
                    "maxBytes": 5 * 1024 * 1024,
                    "backupCount": 5,
                    "encoding": "utf-8",
                },
                "error_file": {
                    "class": "logging.handlers.RotatingFileHandler",
                    "level": "ERROR",
                    "formatter": "detailed",
                    "filename": error_log,
                    "maxBytes": 5 * 1024 * 1024,
                    "backupCount": 5,
                    "encoding": "utf-8",
                },
            },
            "root": {
                "level": log_level,
                "handlers": ["console", "app_file", "error_file"],
            },
            "loggers": {
                "watchfiles.main": {
                    "level": "WARNING",
                    "propagate": False,
                },
            },
        }
    )

    # Keep pyright and static checkers aware of the handler import usage.
    _ = RotatingFileHandler
    if _should_use_color():
        for handler in logging.getLogger().handlers:
            if isinstance(handler, logging.StreamHandler):
                handler.setFormatter(
                    ColorFormatter(
                        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                        datefmt="%Y-%m-%d %H:%M:%S",
                    )
                )
                break

    _CONFIGURED = True
    logging.getLogger(__name__).info(
        "Logger initialized (level=%s, dir=%s)", log_level, log_dir
    )


def get_logger(name: str) -> logging.Logger:
    """Get logger and ensure configuration is initialized."""
    setup_logging()
    return logging.getLogger(name)
