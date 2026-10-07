"""
admin_filler.py — Admin Panel automation for Movie Agent
"""

import time
import random
import traceback
import os
from typing import Dict
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException,
    ElementClickInterceptedException, StaleElementReferenceException,
)
from config import settings
from logger import get_logger

logger = get_logger(__name__)


class AdminFiller:
    EMAIL_ID = "em"
    PASSWORD_ID = "pw"
    LOGIN_BTN_ID = "lb"
    DASHBOARD_ID = "app"
    ERROR_ID = "fe"
    MOVIES_TAB_SELECTOR = "button[data-v='movies']"

    FIELD_TITLE = "f-title"
    FIELD_YEAR = "f-year"
    FIELD_POSTER = "f-poster"
    FIELD_WATCH = "f-watch"
    FIELD_RATING = "f-rating"
    FIELD_DESC = "f-desc"
    FIELD_CAST = "f-cast"
    FIELD_CATEGORY = "f-category"
    FIELD_RATIO = "f-ratio"

    def __init__(self, driver):
        if driver is None:
            raise ValueError("Driver cannot be None")
        self.driver = driver
        self.wait = WebDriverWait(self.driver, 15)
        self._screenshots_dir = "logs/screenshots"
        os.makedirs(self._screenshots_dir, exist_ok=True)

    def _human_delay(self, min_sec=0.5, max_sec=1.5):
        time.sleep(random.uniform(min_sec, max_sec))

    def _human_type(self, element, text, fast=False):
        if not text:
            return
        try:
            element.clear()
            self._human_delay(0.2, 0.5)
            text = str(text)
            if fast or len(text) > 100:
                element.send_keys(text)
            else:
                for char in text:
                    element.send_keys(char)
                    time.sleep(random.uniform(0.02, 0.10))
            self._human_delay(0.2, 0.6)
        except (StaleElementReferenceException, ElementClickInterceptedException) as e:
            logger.warning(f"Type failed: {e}")

    def _screenshot(self, name):
        try:
            timestamp = int(time.time())
            path = os.path.join(self._screenshots_dir, f"{name}_{timestamp}.png")
            self.driver.save_screenshot(path)
            logger.info(f"Screenshot: {path}")
            return path
        except Exception:
            return ""

    def _scroll_into_view(self, element):
        try:
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
            self._human_delay(0.3, 0.7)
        except Exception:
            pass

    def _find_with_wait(self, by, value, timeout=None):
        timeout = timeout or 15
        try:
            return WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((by, value))
            )
        except TimeoutException:
            return None

    def login(self) -> bool:
        try:
            logger.info(f"Opening Admin Panel: {settings.ADMIN_PANEL_URL}")
            self.driver.get(settings.ADMIN_PANEL_URL)
            self._human_delay(3, 5)

            try:
                WebDriverWait(self.driver, 20).until(
                    lambda d: d.find_elements(By.ID, self.EMAIL_ID)
                    or d.find_elements(By.ID, self.DASHBOARD_ID)
                )
            except TimeoutException:
                logger.error("Admin panel did not load.")
                self._screenshot("admin_load_timeout")
                return False

            email_els = self.driver.find_elements(By.ID, self.EMAIL_ID)
            login_visible = email_els and email_els[0].is_displayed() and email_els[0].is_enabled()
            if not login_visible:
                logger.info("Already logged in.")
                return True

            logger.info("Login form detected. Logging in...")
            self._human_type(email_els[0], settings.ADMIN_EMAIL)

            pw_el = self._find_with_wait(By.ID, self.PASSWORD_ID, timeout=10)
            if not pw_el:
                logger.error("Password field not found.")
                return False
            self._human_type(pw_el, settings.ADMIN_PASSWORD)

            login_btn = self._find_with_wait(By.ID, self.LOGIN_BTN_ID, timeout=10)
            if not login_btn:
                logger.error("Login button not found.")
                return False
            self._scroll_into_view(login_btn)
            login_btn.click()

            try:
                WebDriverWait(self.driver, 20).until(
                    lambda d: d.find_element(By.ID, self.DASHBOARD_ID).is_displayed()
                )
                logger.info("Login successful.")
                self._human_delay(2, 4)
                return True
            except TimeoutException:
                try:
                    err = self.driver.find_element(By.ID, "err")
                    if err.text.strip():
                        logger.error(f"Login failed: {err.text.strip()}")
                except NoSuchElementException:
                    logger.error("Login timeout.")
                self._screenshot("admin_login_failed")
                return False

        except Exception as e:
            logger.error(f"Login exception: {e}")
            logger.debug(traceback.format_exc())
            self._screenshot("admin_login_exception")
            return False

    def add_movie(self, movie_data: Dict) -> bool:
        try:
            movies_tab = self.wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, self.MOVIES_TAB_SELECTOR))
            )
            self._scroll_into_view(movies_tab)
            movies_tab.click()
            self._human_delay(1.5, 3.0)

            logger.info(f"Filling form: {movie_data.get('title')}")

            text_fields = [
                (self.FIELD_TITLE, movie_data.get("title", ""), False),
                (self.FIELD_YEAR, str(movie_data.get("year", "")), False),
                (self.FIELD_POSTER, movie_data.get("poster_url", ""), False),
                (self.FIELD_WATCH, movie_data.get("video_url", ""), False),
                (self.FIELD_RATING, movie_data.get("rating", ""), False),
                (self.FIELD_DESC, movie_data.get("description", ""), True),
                (self.FIELD_CAST, movie_data.get("cast", ""), False),
            ]

            for field_id, value, fast in text_fields:
                if not value or value == "N/A":
                    continue
                el = self._find_with_wait(By.ID, field_id, timeout=10)
                if not el:
                    logger.warning(f"Field {field_id} not found.")
                    continue
                self._scroll_into_view(el)
                self._human_type(el, value, fast=fast)

            if movie_data.get("category"):
                try:
                    cat_el = self._find_with_wait(By.ID, self.FIELD_CATEGORY, timeout=5)
                    if cat_el:
                        Select(cat_el).select_by_visible_text(movie_data["category"])
                except Exception as e:
                    logger.warning(f"Category select failed: {e}")

            if movie_data.get("ratio"):
                try:
                    ratio_el = self._find_with_wait(By.ID, self.FIELD_RATIO, timeout=5)
                    if ratio_el:
                        Select(ratio_el).select_by_value(movie_data["ratio"])
                except Exception as e:
                    logger.warning(f"Ratio select failed: {e}")

            save_btn = self._find_save_button()
            if not save_btn:
                logger.error("Save button not found.")
                self._screenshot("save_button_missing")
                return False

            self._scroll_into_view(save_btn)
            self._human_delay(0.5, 1.5)

            try:
                save_btn.click()
            except ElementClickInterceptedException:
                self.driver.execute_script("arguments[0].click();", save_btn)

            logger.info("Save clicked.")
            return self._verify_save()

        except TimeoutException:
            logger.error("Timeout filling form.")
            self._screenshot("admin_fill_timeout")
            return False
        except Exception as e:
            logger.error(f"Fill form error: {e}")
            logger.debug(traceback.format_exc())
            self._screenshot("admin_fill_error")
            return False

    def _find_save_button(self):
        try:
            return WebDriverWait(self.driver, 15).until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//button[contains(translate(text(), 'SAVE', 'save'), 'save')]")
                )
            )
        except TimeoutException:
            return None

    def _verify_save(self):
        self._human_delay(3, 5)
        try:
            error_els = self.driver.find_elements(By.ID, self.ERROR_ID)
            if error_els:
                error_text = error_els[0].text.strip()
                is_hidden = "hidden" in (error_els[0].get_attribute("class") or "")
                if error_text and not is_hidden:
                    logger.error(f"Admin panel error: {error_text}")
                    return False
        except Exception:
            pass
        try:
            title_el = self.driver.find_element(By.ID, self.FIELD_TITLE)
            title_val = title_el.get_attribute("value") or ""
            if title_val.strip() == "":
                logger.info("Form reset — save successful.")
                return True
            logger.warning(f"Form not reset (title: '{title_val}')")
            return False
        except NoSuchElementException:
            logger.info("Title field gone — save successful.")
            return True