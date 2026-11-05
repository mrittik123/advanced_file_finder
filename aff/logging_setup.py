"""Application logging: rotating log file in the app data folder."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .utils import app_data_dir

LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def setup_logging(level: int = logging.INFO, log_dir: Path | None = None,
                  console: bool = False) -> Path:
    """Configure the 'aff' logger. Returns the log file path."""
    log_dir = Path(log_dir) if log_dir else app_data_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "aff.log"
    logger = logging.getLogger("aff")
    logger.setLevel(level)
    logger.handlers.clear()
    fh = RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    fh.setFormatter(logging.Formatter(LOG_FORMAT))
    logger.addHandler(fh)
    if console:
        ch = logging.StreamHandler()
        ch.setFormatter(logging.Formatter(LOG_FORMAT))
        logger.addHandler(ch)
    return log_file
