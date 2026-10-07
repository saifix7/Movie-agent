"""
drive_uploader.py — Google Drive poster upload for Movie Agent
Downloads poster in memory, uploads to Drive, returns direct link.
"""

import io
import re
import time
import requests
from typing import Optional
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from googleapiclient.errors import HttpError

from config import settings
from logger import get_logger

logger = get_logger(__name__)


class DriveUploader:
    """Handles Google Drive poster uploads."""

    SCOPES = ["https://www.googleapis.com/auth/drive.file"]
    MAX_IMAGE_SIZE = 10 * 1024 * 1024       # 10 MB
    DOWNLOAD_TIMEOUT = 30
    UPLOAD_RETRIES = 3

    def __init__(self):
        self.service = None
        self._session = self._build_session()
        self._authenticate_drive()

    # =========================================================
    # SESSION (with retries)
    # =========================================================

    def _build_session(self) -> requests.Session:
        """Build requests session with retry strategy."""
        session = requests.Session()
        retry = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        })
        return session

    # =========================================================
    # AUTH
    # =========================================================

    def _authenticate_drive(self) -> bool:
        """Authenticate with Google Drive. Returns True on success."""
        try:
            creds = service_account.Credentials.from_service_account_file(
                settings.GOOGLE_DRIVE_CREDENTIALS, scopes=self.SCOPES
            )
            self.service = build("drive", "v3", credentials=creds, cache_discovery=False)
            logger.info("Google Drive authenticated.")
            return True
        except FileNotFoundError:
            logger.critical(
                f"Drive credentials not found: {settings.GOOGLE_DRIVE_CREDENTIALS}"
            )
        except Exception as e:
            logger.critical(f"Drive auth failed: {e}")
        return False

    def is_ready(self) -> bool:
        """Check if uploader is ready."""
        return self.service is not None

    # =========================================================
    # MAIN UPLOAD
    # =========================================================

    def upload_poster_from_url(
        self,
        image_url: str,
        title: str,
        folder_id: str,
    ) -> str:
        """
        Download poster (memory only) and upload to Drive.
        Args:
            image_url: direct URL of poster
            title: movie title (used for filename)
            folder_id: Drive folder ID
        Returns: direct link or "" on failure.
        """
        # Validate
        if not self.service:
            logger.error("Drive service not initialized.")
            return ""

        if not image_url or not image_url.startswith(("http://", "https://")):
            logger.warning(f"Invalid image URL: {image_url}")
            return ""

        if not folder_id or not isinstance(folder_id, str) or len(folder_id) < 10:
            logger.warning(f"Invalid folder_id: {folder_id}")
            return ""

        # Download + upload
        try:
            image_bytes, content_type = self._download_image(image_url)
            if not image_bytes:
                return ""

            file_id = self._upload_to_drive(
                image_bytes, content_type, title, folder_id
            )
            if not file_id:
                return ""

            # Make public
            if not self._make_file_public(file_id):
                logger.warning(f"Could not make file public: {file_id}")

            direct_link = f"https://lh3.googleusercontent.com/d/{file_id}"
            logger.info(f"Poster uploaded: {direct_link}")
            return direct_link

        except Exception as e:
            logger.error(f"Upload failed for '{title}': {e}")
            return ""

    # =========================================================
    # DOWNLOAD
    # =========================================================

    def _download_image(self, url: str) -> tuple[bytes, str]:
        """
        Download image into memory.
        Returns (bytes, content_type) or (b"", "").
        """
        try:
            logger.debug(f"Downloading: {url[:80]}...")
            res = self._session.get(url, timeout=self.DOWNLOAD_TIMEOUT)
            res.raise_for_status()

            # Content type check
            content_type = res.headers.get("Content-Type", "").lower().split(";")[0].strip()
            if not content_type.startswith("image/"):
                logger.warning(f"Not an image: {content_type}")
                return b"", ""

            # Size check
            content = res.content
            if len(content) > self.MAX_IMAGE_SIZE:
                logger.warning(
                    f"Image too large: {len(content) / 1024 / 1024:.1f} MB"
                )
                return b"", ""

            if len(content) < 1024:   # < 1 KB — suspicious
                logger.warning(f"Image too small: {len(content)} bytes")
                return b"", ""

            return content, content_type

        except requests.Timeout:
            logger.warning(f"Download timeout: {url[:80]}")
        except requests.RequestException as e:
            logger.warning(f"Download failed: {e}")
        return b"", ""

    # =========================================================
    # UPLOAD
    # =========================================================

    def _upload_to_drive(
        self,
        image_bytes: bytes,
        content_type: str,
        title: str,
        folder_id: str,
    ) -> Optional[str]:
        """Upload image bytes to Drive. Returns file_id or None."""
        file_name = self._build_filename(title, content_type)

        for attempt in range(1, self.UPLOAD_RETRIES + 1):
            try:
                image_stream = io.BytesIO(image_bytes)
                media = MediaIoBaseUpload(
                    image_stream,
                    mimetype=content_type,
                    resumable=True,
                )
                metadata = {"name": file_name, "parents": [folder_id]}

                file = self.service.files().create(
                    body=metadata,
                    media_body=media,
                    fields="id",
                    supportsAllDrives=True,
                ).execute()

                file_id = file.get("id")
                image_stream.close()
                logger.debug(f"Uploaded file_id={file_id}")
                return file_id

            except HttpError as e:
                logger.warning(f"Upload attempt {attempt} failed: {e}")
                if attempt < self.UPLOAD_RETRIES:
                    time.sleep(2 ** attempt)
            except Exception as e:
                logger.error(f"Upload error: {e}")
                break

        return None

    # =========================================================
    # PERMISSIONS
    # =========================================================

    def _make_file_public(self, file_id: str) -> bool:
        """Make Drive file publicly readable. Returns True on success."""
        try:
            self.service.permissions().create(
                fileId=file_id,
                body={"type": "anyone", "role": "reader"},
                fields="id",
                supportsAllDrives=True,
            ).execute()
            return True
        except HttpError as e:
            logger.error(f"Permission error: {e}")
            return False

    # =========================================================
    # HELPERS
    # =========================================================

    def _build_filename(self, title: str, content_type: str) -> str:
        """Build safe, unique filename."""
        # Sanitize
        safe = re.sub(r"[^a-zA-Z0-9 _-]", "", title or "").strip()
        safe = re.sub(r"\s+", "_", safe)[:50]
        if not safe:
            safe = "poster"

        # Extension from content type
        ext_map = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
            "image/gif": ".gif",
        }
        ext = ext_map.get(content_type, ".jpg")

        # Unique (avoid Drive duplicate)
        timestamp = int(time.time())
        return f"{safe}_{timestamp}{ext}"

    # =========================================================
    # TEST
    # =========================================================

    def test_connection(self) -> bool:
        """Test Drive connectivity."""
        if not self.service:
            return False
        try:
            self.service.files().list(pageSize=1, fields="files(id)").execute()
            return True
        except Exception as e:
            logger.error(f"Drive test failed: {e}")
            return False