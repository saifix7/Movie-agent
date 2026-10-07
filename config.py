"""
config.py — Configuration loader for Movie Agent
Loads settings from .env, validates them, and exposes as `settings`.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env
load_dotenv()


class Config:
    """Application configuration loaded from environment variables."""

    # =========================================================
    # FIREBASE
    # =========================================================
    FIREBASE_PROJECT_ID: str = os.getenv("FIREBASE_PROJECT_ID", "earn-learn-f98ef")
    FIREBASE_SERVICE_ACCOUNT: str = os.getenv(
        "FIREBASE_SERVICE_ACCOUNT", "serviceAccountKey.json"
    )

    # =========================================================
    # GOOGLE DRIVE
    # =========================================================
    GOOGLE_DRIVE_CREDENTIALS: str = os.getenv(
        "GOOGLE_DRIVE_CREDENTIALS", "credentials.json"
    )
    GOOGLE_DRIVE_FOLDER_ID: str = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")

    # =========================================================
    # ADMIN PANEL
    # =========================================================
    ADMIN_PANEL_URL: str = os.getenv("ADMIN_PANEL_URL", "").strip()
    ADMIN_EMAIL: str = os.getenv("ADMIN_EMAIL", "").strip()
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "").strip()

    # =========================================================
    # SCRAPER SETTINGS
    # =========================================================
    HEADLESS: bool = os.getenv("HEADLESS", "true").strip().lower() in (
        "true", "1", "yes", "y"
    )
    PAGE_LOAD_TIMEOUT: int = int(os.getenv("PAGE_LOAD_TIMEOUT", "45"))
    MIN_DELAY: float = float(os.getenv("MIN_DELAY", "2.0"))
    MAX_DELAY: float = float(os.getenv("MAX_DELAY", "5.0"))

    # =========================================================
    # AGENT SETTINGS
    # =========================================================
    CHECK_INTERVAL: int = int(os.getenv("CHECK_INTERVAL", "30"))
    DELAY_BETWEEN_MOVIES: int = int(os.getenv("DELAY_BETWEEN_MOVIES", "300"))
    DAILY_POST_LIMIT: int = int(os.getenv("DAILY_POST_LIMIT", "100"))
    MAX_RETRIES_PER_MOVIE: int = int(os.getenv("MAX_RETRIES_PER_MOVIE", "2"))

    # =========================================================
    # LOGGING
    # =========================================================
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
    LOG_DIR: str = os.getenv("LOG_DIR", "logs")

    # =========================================================
    # VALIDATION
    # =========================================================
    def validate(self) -> tuple[bool, list[str]]:
        """
        Validate required settings.
        Returns: (is_valid, list_of_errors)
        """
        errors = []

        # Admin panel
        if not self.ADMIN_PANEL_URL:
            errors.append("ADMIN_PANEL_URL is missing.")
        elif not self.ADMIN_PANEL_URL.startswith(("http://", "https://")):
            errors.append("ADMIN_PANEL_URL must start with http:// or https://")

        if not self.ADMIN_EMAIL:
            errors.append("ADMIN_EMAIL is missing.")
        elif "@" not in self.ADMIN_EMAIL:
            errors.append("ADMIN_EMAIL is not a valid email.")

        if not self.ADMIN_PASSWORD:
            errors.append("ADMIN_PASSWORD is missing.")
        elif len(self.ADMIN_PASSWORD) < 6:
            errors.append("ADMIN_PASSWORD must be at least 6 characters.")

        # Files
        if not Path(self.FIREBASE_SERVICE_ACCOUNT).exists():
            errors.append(
                f"Firebase service account not found: {self.FIREBASE_SERVICE_ACCOUNT}"
            )

        if not Path(self.GOOGLE_DRIVE_CREDENTIALS).exists():
            errors.append(
                f"Google Drive credentials not found: {self.GOOGLE_DRIVE_CREDENTIALS}"
            )

        # Numeric
        if self.PAGE_LOAD_TIMEOUT < 5:
            errors.append("PAGE_LOAD_TIMEOUT must be >= 5 seconds.")
        if self.MIN_DELAY < 0:
            errors.append("MIN_DELAY cannot be negative.")
        if self.MAX_DELAY < self.MIN_DELAY:
            errors.append("MAX_DELAY must be >= MIN_DELAY.")
        if self.DAILY_POST_LIMIT < 1:
            errors.append("DAILY_POST_LIMIT must be >= 1.")

        return len(errors) == 0, errors

    # =========================================================
    # DEBUG
    # =========================================================
    def summary(self) -> str:
        """Return a summary of loaded config (without secrets)."""
        return (
            f"\n{'=' * 50}\n"
            f"CONFIG SUMMARY\n"
            f"{'=' * 50}\n"
            f"Firebase Project   : {self.FIREBASE_PROJECT_ID}\n"
            f"Firebase Key File  : {self.FIREBASE_SERVICE_ACCOUNT}\n"
            f"Drive Credentials  : {self.GOOGLE_DRIVE_CREDENTIALS}\n"
            f"Drive Folder ID    : {self.GOOGLE_DRIVE_FOLDER_ID or '(not set)'}\n"
            f"Admin Panel URL    : {self.ADMIN_PANEL_URL or '(not set)'}\n"
            f"Admin Email        : {self.ADMIN_EMAIL or '(not set)'}\n"
            f"Admin Password     : {'*' * len(self.ADMIN_PASSWORD) if self.ADMIN_PASSWORD else '(not set)'}\n"
            f"Headless Mode      : {self.HEADLESS}\n"
            f"Page Load Timeout  : {self.PAGE_LOAD_TIMEOUT}s\n"
            f"Delay Range        : {self.MIN_DELAY}s - {self.MAX_DELAY}s\n"
            f"Check Interval     : {self.CHECK_INTERVAL}s\n"
            f"Delay Between      : {self.DELAY_BETWEEN_MOVIES}s\n"
            f"Daily Post Limit   : {self.DAILY_POST_LIMIT}\n"
            f"Max Retries        : {self.MAX_RETRIES_PER_MOVIE}\n"
            f"Log Level          : {self.LOG_LEVEL}\n"
            f"Log Directory      : {self.LOG_DIR}\n"
            f"{'=' * 50}\n"
        )


# Singleton
settings = Config()