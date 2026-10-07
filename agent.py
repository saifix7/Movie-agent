"""
agent.py — Movie Agent main orchestrator
Ties together scraper, parser, drive uploader, and admin filler.
Controls rate limiting and daily job limits via APScheduler.
"""

import time
import traceback
from datetime import datetime, date
from typing import Optional

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

from database import db_client
from scraper import WebScraper
from parser import MovieParser
from drive_uploader import DriveUploader
from admin_filler import AdminFiller
from logger import get_logger

logger = get_logger(__name__)


# =========================================================
# CONFIG / CONSTANTS
# =========================================================

CHECK_INTERVAL_SECONDS = 30          # Firebase check frequency
DELAY_BETWEEN_MOVIES = 300           # 5 minutes
DAILY_POST_LIMIT = 100               # Max movies per day
MAX_RETRIES_PER_MOVIE = 2            # Retry attempts on failure
DEFAULT_LINK_SELECTOR = "a"          # CSS selector for movie cards


class MovieAgent:
    """
    Master orchestrator for Movie Agent.
    Handles: config read, status check, scraper lifecycle,
    rate limiting, and daily post counter.
    """

    def __init__(self):
        self.parser = MovieParser()
        self.drive_uploader = DriveUploader()
        self.current_date: date = datetime.now().date()
        self.daily_posts: int = 0
        self.is_working: bool = False
        self.scraper: Optional[WebScraper] = None

        logger.info("MovieAgent initialized.")

    # =========================================================
    # DAILY COUNTER
    # =========================================================

    def _reset_daily_counter_if_needed(self) -> None:
        """Reset daily post counter if date changed."""
        today = datetime.now().date()
        if self.current_date != today:
            logger.info(
                f"New day started. Resetting daily counter "
                f"({self.current_date} → {today})."
            )
            self.current_date = today
            self.daily_posts = 0

    # =========================================================
    # CONFIG VALIDATION
    # =========================================================

    def _validate_config(self, config: dict) -> tuple[bool, str]:
        """
        Validate bot config.
        Returns: (is_valid, error_message)
        """
        if not config:
            return False, "Empty config from Firebase."

        target_url = config.get("target_website", "").strip()
        folder_id = config.get("drive_folder_id", "").strip()

        if not target_url:
            return False, "target_website is missing."
        if not target_url.startswith(("http://", "https://")):
            return False, "target_website is not a valid URL."
        if not folder_id:
            return False, "drive_folder_id is missing."

        return True, ""

    # =========================================================
    # MAIN WORKFLOW
    # =========================================================

    def run_workflow(self) -> None:
        """Main automation loop — runs every 30 seconds."""
        try:
            # 1. Fetch config
            config = db_client.get_bot_config() or {}
            status = config.get("status", "stopped")

            if status != "running":
                logger.debug("Agent stopped. Waiting for admin command...")
                return

            # 2. Prevent concurrent runs
            if self.is_working:
                logger.debug("Agent already running. Skipping tick.")
                return

            # 3. Reset daily counter if needed
            self._reset_daily_counter_if_needed()

            # 4. Daily limit check
            if self.daily_posts >= DAILY_POST_LIMIT:
                logger.warning(
                    f"Daily limit reached ({self.daily_posts}/{DAILY_POST_LIMIT}). "
                    f"Auto-stopping agent."
                )
                db_client.update_bot_status("stopped")
                db_client.log_action(
                    "RATE_LIMIT",
                    f"Daily limit ({DAILY_POST_LIMIT}) reached."
                )
                return

            # 5. Validate config
            is_valid, error = self._validate_config(config)
            if not is_valid:
                logger.error(f"Config invalid: {error}")
                db_client.update_bot_status("stopped")
                db_client.log_action("CONFIG_ERROR", error)
                return

            # 6. Extract config values
            target_url = config["target_website"].strip()
            folder_id = config["drive_folder_id"].strip()
            videos_to_add = max(1, int(config.get("videos_to_add", 1)))
            link_selector = config.get("link_selector", DEFAULT_LINK_SELECTOR).strip() or DEFAULT_LINK_SELECTOR

            # 7. Run batch
            self._run_batch(
                target_url=target_url,
                folder_id=folder_id,
                videos_to_add=videos_to_add,
                link_selector=link_selector,
            )

        except Exception as e:
            logger.error(f"Workflow error: {e}")
            logger.debug(traceback.format_exc())
            try:
                db_client.log_action("WORKFLOW_ERROR", str(e)[:200])
            except Exception:
                pass
            self.is_working = False

    # =========================================================
    # BATCH RUNNER
    # =========================================================

    def _run_batch(
        self,
        target_url: str,
        folder_id: str,
        videos_to_add: int,
        link_selector: str,
    ) -> None:
        """Run one batch of scraping + upload + save."""
        self.is_working = True
        success_count = 0

        db_client.log_action(
            "AGENT_START",
            f"Batch started: {videos_to_add} movies from {target_url}"
        )
        logger.info(
            f"=== Batch started: target={videos_to_add} movies | url={target_url} ==="
        )

        self.scraper = WebScraper()

        try:
            # Start browser session
            if not self.scraper.start_session():
                raise RuntimeError("Failed to start WebDriver session.")

            # Admin login (before scraping — fail fast)
            admin_filler = AdminFiller(self.scraper.driver)
            if not admin_filler.login():
                raise RuntimeError("Admin panel login failed.")

            # Fetch movie links (extra 2x for retries)
            fetch_count = min(videos_to_add * 2, DAILY_POST_LIMIT - self.daily_posts)
            logger.info(f"Fetching up to {fetch_count} movie links...")
            links = self.scraper.fetch_movie_links(
                target_url, link_selector, max_count=fetch_count
            )

            if not links:
                raise RuntimeError("No movie links found.")

            logger.info(f"Got {len(links)} links. Processing...")

            # Process each link
            for idx, link in enumerate(links, 1):
                if success_count >= videos_to_add:
                    logger.info(f"Target reached ({success_count}/{videos_to_add}).")
                    break

                if self.daily_posts >= DAILY_POST_LIMIT:
                    logger.warning("Daily limit hit mid-batch.")
                    break

                logger.info(
                    f"--- [{idx}] Processing: {link} "
                    f"(success: {success_count}/{videos_to_add}) ---"
                )

                # Retry logic per movie
                if self._process_single_movie(
                    link, folder_id, admin_filler, scraper_ref=self.scraper
                ):
                    success_count += 1
                    self.daily_posts += 1
                    logger.info(f"✅ Success: {success_count}/{videos_to_add}")

                    # Human-like delay (except last)
                    if success_count < videos_to_add:
                        logger.info(
                            f"⏳ Waiting {DELAY_BETWEEN_MOVIES}s before next movie..."
                        )
                        time.sleep(DELAY_BETWEEN_MOVIES)
                else:
                    logger.warning(f"❌ Failed: {link}")

            logger.info(
                f"=== Batch complete: {success_count}/{videos_to_add} movies added ==="
            )
            db_client.log_action(
                "AGENT_STOP",
                f"Batch finished. Added {success_count} movies."
            )

        except Exception as e:
            logger.error(f"Batch error: {e}")
            logger.debug(traceback.format_exc())
            db_client.log_action("BATCH_ERROR", str(e)[:200])

        finally:
            # Cleanup
            if self.scraper:
                try:
                    self.scraper.close_session()
                except Exception as e:
                    logger.warning(f"Scraper close error: {e}")
                self.scraper = None

            # Auto-stop agent in Firebase
            try:
                db_client.update_bot_status("stopped")
            except Exception as e:
                logger.warning(f"Failed to update status: {e}")

            self.is_working = False
            logger.info("=== Agent ready. ===")

    # =========================================================
    # SINGLE MOVIE PROCESSOR
    # =========================================================

    def _process_single_movie(
        self,
        link: str,
        folder_id: str,
        admin_filler: AdminFiller,
        scraper_ref: WebScraper,
    ) -> bool:
        """
        Process one movie with retries.
        Returns True if successfully added.
        """
        for attempt in range(1, MAX_RETRIES_PER_MOVIE + 1):
            try:
                if attempt > 1:
                    logger.info(f"Retry {attempt}/{MAX_RETRIES_PER_MOVIE}: {link}")

                # A. Scrape page
                html = scraper_ref.fetch_with_retry(link, retries=2)
                if not html:
                    logger.warning(f"Page fetch failed: {link}")
                    continue

                # B. Parse
                movie_data = self.parser.parse_movie_page(html, base_url=link)

                if not movie_data.get("title") or movie_data["title"] == "Unknown Title":
                    logger.warning(f"Title not found: {link}")
                    continue

                if not movie_data.get("video_url"):
                    logger.warning(f"Video URL not found: {link}")
                    continue

                logger.info(f"Parsed: {movie_data['title']} ({movie_data.get('year', '')})")

                # C. Upload poster to Drive
                if movie_data.get("poster_url"):
                    try:
                        drive_link = self.drive_uploader.upload_poster_from_url(
                            movie_data["poster_url"],
                            movie_data["title"],
                            folder_id,
                        )
                        if drive_link:
                            movie_data["poster_url"] = drive_link
                            logger.info(f"Poster uploaded: {drive_link}")
                    except Exception as e:
                        logger.warning(f"Poster upload failed: {e}")

                # D. Fill admin panel
                if admin_filler.add_movie(movie_data):
                    db_client.log_action(
                        "MOVIE_ADDED",
                        f"{movie_data['title']} ({movie_data.get('year', '')})"
                    )
                    return True

                logger.warning(f"Admin fill failed: {movie_data['title']}")

            except Exception as e:
                logger.error(f"Movie processing error (attempt {attempt}): {e}")
                logger.debug(traceback.format_exc())

        # All retries failed
        try:
            db_client.log_action("MOVIE_FAILED", f"All retries failed: {link[:100]}")
        except Exception:
            pass
        return False

    # =========================================================
    # SHUTDOWN
    # =========================================================

    def shutdown(self) -> None:
        """Graceful shutdown."""
        logger.info("Shutting down MovieAgent...")
        if self.scraper:
            try:
                self.scraper.close_session()
            except Exception:
                pass
        try:
            db_client.update_bot_status("stopped")
        except Exception:
            pass
        logger.info("Shutdown complete.")


# =========================================================
# ENTRY POINT
# =========================================================

def main() -> None:
    logger.info("=" * 50)
    logger.info("Starting Movie Agent Service...")
    logger.info(f"Check interval: {CHECK_INTERVAL_SECONDS}s")
    logger.info(f"Daily limit: {DAILY_POST_LIMIT} movies")
    logger.info(f"Delay between movies: {DELAY_BETWEEN_MOVIES}s")
    logger.info("=" * 50)

    agent = MovieAgent()
    scheduler = BlockingScheduler()

    scheduler.add_job(
        agent.run_workflow,
        trigger=IntervalTrigger(seconds=CHECK_INTERVAL_SECONDS),
        id="movie_agent_workflow",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=10,
    )

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Stop signal received.")
    finally:
        agent.shutdown()
        logger.info("Movie Agent Service stopped.")


if __name__ == "__main__":
    main()