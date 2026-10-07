"""
logger.py — Logging setup for Movie Agent
Rotating file handler + console handler with UTF-8 encoding.
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from config import settings


# =========================================================
# LOG PATHS
# =========================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, settings.LOG_DIR)
LOG_FILE = os.path.join(LOG_DIR, "agent.log")

# Ensure directory exists
try:
    os.makedirs(LOG_DIR, exist_ok=True)
except OSError as e:
    print(f"[LOGGER] Failed to create log dir '{LOG_DIR}': {e}", file=sys.stderr)


# =========================================================
# FORMATTER
# =========================================================

FILE_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


# =========================================================
# ROOT SETUP (ek baar)
# =========================================================

_root_configured = False


def _configure_root():
    """Configure root logger once (fallback for non-module logs)."""
    global _root_configured
    if _root_configured:
        return
    _root_configured = True

    level = getattr(logging, settings.LOG_LEVEL, logging.INFO)
    logging.basicConfig(
        level=level,
        format=FILE_FORMAT,
        datefmt=DATE_FORMAT,
        stream=sys.stdout,
    )


# =========================================================
# GET LOGGER
# =========================================================

def get_logger(module_name: str) -> logging.Logger:
    """
    Get a configured logger for the given module.
    Adds file + console handlers (once per logger).
    """
    _configure_root()

    logger = logging.getLogger(module_name)

    # Already configured
    if logger.handlers:
        return logger

    # Set level
    level = getattr(logging, settings.LOG_LEVEL, logging.INFO)
    logger.setLevel(level)

    formatter = logging.Formatter(FILE_FORMAT, datefmt=DATE_FORMAT)

    # -------- File Handler --------
    try:
        file_handler = RotatingFileHandler(
            LOG_FILE,
            maxBytes=5 * 1024 * 1024,   # 5 MB
            backupCount=3,
            encoding="utf-8",
            delay=True,                 # file tab bane jab pehli log likhe
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(level)
        logger.addHandler(file_handler)
    except Exception as e:
        print(f"[LOGGER] File handler failed: {e}", file=sys.stderr)

    # -------- Console Handler --------
    try:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        console_handler.setLevel(level)
        logger.addHandler(console_handler)
    except Exception as e:
        print(f"[LOGGER] Console handler failed: {e}", file=sys.stderr)

    # Prevent duplicate logs via root
    logger.propagate = False

    return logger


# =========================================================
# UTILITY — silence noisy libraries
# =========================================================

def silence_noisy_loggers():
    """Reduce verbosity of common noisy loggers."""
    for name in (
        "selenium",
        "urllib3",
        "google",
        "googleapiclient",
        "google.auth",
        "firebase_admin",
        "apscheduler",
        "undetected_chromedriver",
    ):
        logging.getLogger(name).setLevel(logging.WARNING)