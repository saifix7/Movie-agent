"""
scraper.py — Web scraper for Movie Agent
Uses undetected-chromedriver for bot-detection bypass.
Handles: navigation, human-like behaviour, video URL extraction, screenshots.
"""

import os
import time
import json
import random
import pickle
import traceback
from typing import Optional, List, Dict
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from config import settings
from logger import get_logger

logger = get_logger(__name__)


# Random User Agents (rotation ke liye)
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]


class WebScraper:
    """
    Handles all browser interactions using undetected-chromedriver.
    Simulates human behaviour to bypass bot detection.
    """

    def __init__(self):
        self.driver: Optional[uc.Chrome] = None
        self.cookies_file = "logs/cookies.pkl"

    # =========================================================
    # SESSION MANAGEMENT
    # =========================================================

    def start_session(self) -> bool:
        """
        Initialize Selenium WebDriver with anti-detection options.
        Returns True on success, False on failure.
        """
        try:
            logger.info("Initializing Selenium WebDriver...")

            options = uc.ChromeOptions()

            # Headless mode (Render ke liye)
            if settings.HEADLESS:
                options.add_argument('--headless=new')
                logger.info("Running in headless mode")

            # Anti-detection arguments
            options.add_argument('--disable-gpu')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--window-size=1920,1080')
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_argument('--disable-infobars')
            options.add_argument('--disable-extensions')
            options.add_argument('--disable-popup-blocking')
            options.add_argument('--ignore-certificate-errors')
            options.add_argument('--log-level=3')

            # Random User Agent
            ua = random.choice(USER_AGENTS)
            options.add_argument(f'--user-agent={ua}')
            logger.info(f"User-Agent set: {ua[:60]}...")

            # Enable performance logging (video URL extraction ke liye)
            options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})

            # Start driver (version_main auto-detect)
            self.driver = uc.Chrome(options=options)
            self.driver.set_page_load_timeout(settings.PAGE_LOAD_TIMEOUT)

            # Hide webdriver flag
            self.driver.execute_cdp_cmd(
                'Page.addScriptToEvaluateOnNewDocument',
                {'source': 'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'}
            )

            logger.info("WebDriver initialized successfully.")
            return True

        except Exception as e:
            logger.error(f"Failed to start WebDriver: {e}")
            logger.debug(traceback.format_exc())
            return False

    def close_session(self) -> None:
        """Safely close the WebDriver instance."""
        try:
            if self.driver:
                self.save_cookies()
                self.driver.quit()
                logger.info("WebDriver closed safely.")
        except Exception as e:
            logger.error(f"Error closing WebDriver: {e}")
        finally:
            self.driver = None

    # =========================================================
    # HUMAN-LIKE BEHAVIOUR
    # =========================================================

    def _human_delay(self, min_sec: float = 2.0, max_sec: float = 5.0) -> None:
        """Random delay to mimic human reading/waiting time."""
        time.sleep(random.uniform(min_sec, max_sec))

    def _human_behavior(self) -> None:
        """Simulate human scrolling and mouse movements."""
        try:
            # Random scroll down
            scroll = random.randint(300, 800)
            self.driver.execute_script(f"window.scrollBy(0, {scroll});")
            self._human_delay(1.0, 2.5)

            # Random scroll up slightly
            scroll = random.randint(-200, -50)
            self.driver.execute_script(f"window.scrollBy(0, {scroll});")
            self._human_delay(1.0, 2.0)

            # Random mouse movement (safe try)
            try:
                body = self.driver.find_element(By.TAG_NAME, "body")
                action = ActionChains(self.driver)
                action.move_to_element_with_offset(
                    body,
                    random.randint(10, 100),
                    random.randint(10, 100)
                ).perform()
            except Exception:
                pass  # Body na mile toh skip

        except Exception as e:
            logger.warning(f"Minor error during human behaviour: {e}")

    # =========================================================
    # COOKIES
    # =========================================================

    def save_cookies(self) -> None:
        """Save cookies to file."""
        try:
            if self.driver:
                os.makedirs("logs", exist_ok=True)
                with open(self.cookies_file, "wb") as f:
                    pickle.dump(self.driver.get_cookies(), f)
                logger.info("Cookies saved.")
        except Exception as e:
            logger.warning(f"Cookie save failed: {e}")

    def load_cookies(self) -> None:
        """Load cookies from file."""
        try:
            if os.path.exists(self.cookies_file) and self.driver:
                with open(self.cookies_file, "rb") as f:
                    cookies = pickle.load(f)
                for cookie in cookies:
                    try:
                        self.driver.add_cookie(cookie)
                    except Exception:
                        pass
                logger.info(f"Loaded {len(cookies)} cookies.")
        except Exception as e:
            logger.warning(f"Cookie load failed: {e}")

    # =========================================================
    # SCREENSHOTS
    # =========================================================

    def take_screenshot(self, name: str = "error") -> str:
        """Take screenshot for debugging."""
        try:
            os.makedirs("logs/screenshots", exist_ok=True)
            timestamp = int(time.time())
            path = f"logs/screenshots/{name}_{timestamp}.png"
            self.driver.save_screenshot(path)
            logger.info(f"Screenshot saved: {path}")
            return path
        except Exception as e:
            logger.error(f"Screenshot failed: {e}")
            return ""

    # =========================================================
    # PAGE NAVIGATION
    # =========================================================

    def fetch_page_html(self, url: str) -> Optional[str]:
        """
        Navigate to URL, human-like actions, return HTML.
        Returns None on failure.
        """
        try:
            logger.info(f"Navigating to: {url}")
            self.driver.get(url)
            self._human_delay(3.0, 6.0)
            self._human_behavior()
            return self.driver.page_source

        except Exception as e:
            logger.error(f"Error loading page {url}: {e}")
            self.take_screenshot("page_load_error")
            return None

    def fetch_with_retry(self, url: str, retries: int = 3) -> Optional[str]:
        """Fetch page with retry logic."""
        for attempt in range(retries):
            html = self.fetch_page_html(url)
            if html:
                return html
            logger.warning(f"Retry {attempt + 1}/{retries} for {url}")
            time.sleep(5)
        return None

    # =========================================================
    # MOVIE LINKS
    # =========================================================

    def fetch_movie_links(self, url: str, selector: str, max_count: int) -> List[str]:
        """
        Fetch movie links from main page.
        Args:
            url: page URL
            selector: CSS selector for movie cards
            max_count: max links to fetch
        Returns: list of URLs
        """
        try:
            logger.info(f"Fetching movie links from: {url}")
            self.driver.get(url)
            self._human_delay(4.0, 7.0)
            self._human_behavior()

            # Wait for elements
            try:
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
            except Exception:
                logger.warning(f"Selector not found: {selector}")

            elements = self.driver.find_elements(By.CSS_SELECTOR, selector)

            links = []
            for el in elements:
                try:
                    href = el.get_attribute('href')
                    if href and href not in links:
                        links.append(href)
                    if len(links) >= max_count:
                        break
                except Exception:
                    continue

            logger.info(f"Found {len(links)} movie links.")
            return links

        except Exception as e:
            logger.error(f"Error fetching links: {e}")
            self.take_screenshot("fetch_links_error")
            return []

    # =========================================================
    # VIDEO URL EXTRACTION
    # =========================================================

    def extract_video_url(self) -> str:
        """
        Extract video URL from current page.
        Tries multiple methods: video tag, source tag, iframe, network logs.
        Returns URL string or empty string.
        """
        # Method 1: Direct video tag
        url = self._get_video_from_tag()
        if url:
            logger.info(f"Video URL found (tag): {url}")
            return url

        # Method 2: Iframe
        url = self._get_video_from_iframe()
        if url:
            logger.info(f"Video URL found (iframe): {url}")
            return url

        # Method 3: Network logs
        url = self._get_video_from_network_logs()
        if url:
            logger.info(f"Video URL found (network): {url}")
            return url

        logger.warning("Video URL not found.")
        return ""

    def _get_video_from_tag(self) -> str:
        """Extract video URL from <video> or <source> tag."""
        try:
            # Try video tag
            videos = self.driver.find_elements(By.TAG_NAME, "video")
            for video in videos:
                src = video.get_attribute("src")
                if src:
                    return src
                # Try source child
                sources = video.find_elements(By.TAG_NAME, "source")
                for source in sources:
                    src = source.get_attribute("src")
                    if src:
                        return src

            # Try standalone source tag
            sources = self.driver.find_elements(By.TAG_NAME, "source")
            for source in sources:
                src = source.get_attribute("src")
                if src:
                    return src
        except Exception:
            pass
        return ""

    def _get_video_from_iframe(self) -> str:
        """Extract video URL from iframe."""
        try:
            iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
            for iframe in iframes:
                src = iframe.get_attribute("src")
                if src and ("video" in src.lower() or "embed" in src.lower() or "player" in src.lower()):
                    return src

                # Switch to iframe and look for video
                try:
                    self.driver.switch_to.frame(iframe)
                    videos = self.driver.find_elements(By.TAG_NAME, "video")
                    for video in videos:
                        src = video.get_attribute("src")
                        if src:
                            self.driver.switch_to.default_content()
                            return src
                    self.driver.switch_to.default_content()
                except Exception:
                    try:
                        self.driver.switch_to.default_content()
                    except Exception:
                        pass
        except Exception:
            pass
        return ""

    def _get_video_from_network_logs(self) -> str:
        """Extract video URL from Chrome performance logs."""
        try:
            logs = self.driver.get_log('performance')
            video_patterns = ['.mp4', '.m3u8', '.webm', '.mkv', 'videoplayback', 'video/']
            for log in reversed(logs):  # Reverse — latest first
                try:
                    msg = json.loads(log['message'])
                    method = msg.get('message', {}).get('method', '')
                    if method == 'Network.responseReceived':
                        url = msg['message']['params']['response']['url']
                        if any(p in url.lower() for p in video_patterns):
                            return url
                except Exception:
                    continue
        except Exception:
            pass
        return ""

    # =========================================================
    # PAGE ELEMENTS
    # =========================================================

    def get_element_text(self, selector: str, attribute: str = "textContent") -> str:
        """Get text or attribute from element."""
        try:
            el = self.driver.find_element(By.CSS_SELECTOR, selector)
            if attribute == "textContent":
                return el.text.strip()
            return el.get_attribute(attribute) or ""
        except Exception:
            return ""

    def element_exists(self, selector: str) -> bool:
        """Check if element exists."""
        try:
            self.driver.find_element(By.CSS_SELECTOR, selector)
            return True
        except Exception:
            return False

    def click_element(self, selector: str) -> bool:
        """Click element by CSS selector."""
        try:
            el = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
            )
            el.click()
            self._human_delay(1.0, 2.0)
            return True
        except Exception as e:
            logger.warning(f"Click failed for {selector}: {e}")
            return False

    def fill_input(self, selector: str, value: str) -> bool:
        """Fill input field with value."""
        try:
            el = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, selector))
            )
            el.clear()
            # Human-like typing
            for char in value:
                el.send_keys(char)
                time.sleep(random.uniform(0.02, 0.08))
            return True
        except Exception as e:
            logger.warning(f"Fill failed for {selector}: {e}")
            return False