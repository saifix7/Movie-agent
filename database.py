"""
database.py — Firebase Realtime Database client for Movie Agent
"""

import time
from typing import Dict, Any, Optional
from datetime import datetime

import firebase_admin
from firebase_admin import credentials, db

from config import settings
from logger import get_logger

logger = get_logger(__name__)

MAX_LOGS = 500
RETRY_ATTEMPTS = 3
RETRY_DELAY = 2

DEFAULT_BOT_CONFIG = {
    "status": "stopped",
    "target_website": "",
    "drive_folder_id": "",
    "videos_to_add": 1,
    "posts_today": 0,
    "last_run": "",
}


class FirebaseDB:
    def __init__(self):
        self._initialized = False
        self._refs = {}

    def _ensure_initialized(self) -> bool:
        if self._initialized:
            return True
        try:
            if not firebase_admin._apps:
                cred = credentials.Certificate(settings.FIREBASE_SERVICE_ACCOUNT)
                db_url = settings.FIREBASE_DATABASE_URL or (
                    f"https://{settings.FIREBASE_PROJECT_ID}-default-rtdb.firebaseio.com"
                )
                firebase_admin.initialize_app(cred, {"databaseURL": db_url})
                logger.info(f"Firebase initialized: {settings.FIREBASE_PROJECT_ID}")
            self._initialized = True
            return True
        except Exception as e:
            logger.critical(f"Firebase init failed: {e}")
            return False

    def _ref(self, path):
        if path not in self._refs:
            self._refs[path] = db.reference(path)
        return self._refs[path]

    def _with_retry(self, fn, *args, **kwargs):
        for attempt in range(1, RETRY_ATTEMPTS + 1):
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                if attempt == RETRY_ATTEMPTS:
                    logger.error(f"Failed after {attempt} attempts: {e}")
                    raise
                logger.warning(f"Attempt {attempt} failed: {e}. Retrying...")
                time.sleep(RETRY_DELAY)
        return None

    def get_bot_config(self) -> Dict[str, Any]:
        if not self._ensure_initialized():
            return DEFAULT_BOT_CONFIG.copy()
        try:
            data = self._with_retry(lambda: self._ref("bot_config").get())
            config = DEFAULT_BOT_CONFIG.copy()
            if isinstance(data, dict):
                config.update(data)
            return config
        except Exception as e:
            logger.error(f"get_bot_config failed: {e}")
            return DEFAULT_BOT_CONFIG.copy()

    def update_bot_status(self, status: str) -> bool:
        if not self._ensure_initialized():
            return False
        try:
            self._with_retry(lambda: self._ref("bot_config").update({
                "status": status,
                "last_run": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }))
            logger.info(f"Bot status: {status}")
            return True
        except Exception as e:
            logger.error(f"update_bot_status failed: {e}")
            return False

    def movie_exists(self, title: str, year: str = "") -> bool:
        if not self._ensure_initialized():
            return False
        try:
            movies = self._with_retry(lambda: self._ref("movies").get())
            if not isinstance(movies, dict):
                return False
            title_lower = title.strip().lower()
            year_str = str(year).strip()
            for movie in movies.values():
                if not isinstance(movie, dict):
                    continue
                if movie.get("title", "").strip().lower() == title_lower:
                    if not year_str or str(movie.get("year", "")).strip() == year_str:
                        return True
            return False
        except Exception as e:
            logger.warning(f"movie_exists check failed: {e}")
            return False

    def add_movie(self, movie_data: Dict[str, Any]) -> bool:
        if not self._ensure_initialized():
            return False
        title = movie_data.get("title", "").strip()
        year = str(movie_data.get("year", "")).strip()
        if not title:
            return False
        if self.movie_exists(title, year):
            logger.info(f"Movie already exists: {title} ({year})")
            return False
        try:
            payload = dict(movie_data)
            payload["added_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            payload["added_by"] = "agent"
            self._with_retry(lambda: self._ref("movies").push(payload))
            logger.info(f"Movie added: {title} ({year})")
            return True
        except Exception as e:
            logger.error(f"add_movie failed: {e}")
            return False

    def log_action(self, action: str, message: str) -> None:
        if not self._ensure_initialized():
            return
        try:
            self._ref("agent_logs").push({
                "action": action,
                "message": str(message)[:500],
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })
            self._trim_logs()
        except Exception as e:
            logger.warning(f"log_action failed: {e}")

    def _trim_logs(self):
        try:
            logs = self._ref("agent_logs").get()
            if not isinstance(logs, dict) or len(logs) <= MAX_LOGS:
                return
            sorted_keys = sorted(logs.keys())
            excess = len(sorted_keys) - MAX_LOGS
            for key in sorted_keys[:excess]:
                self._ref(f"agent_logs/{key}").delete()
        except Exception:
            pass

    def is_connected(self) -> bool:
        if not self._ensure_initialized():
            return False
        try:
            self._ref("bot_config").get()
            return True
        except Exception:
            return False


_db_instance = None

def get_db() -> FirebaseDB:
    global _db_instance
    if _db_instance is None:
        _db_instance = FirebaseDB()
    return _db_instance

db_client = get_db()