"""Bilibili Browser - Autonomous video browsing for AFK streaming."""

from __future__ import annotations

import os
import random
import threading
import time
from typing import Optional

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    from selenium.webdriver.edge.options import Options as EdgeOptions
    from selenium.common.exceptions import (
        NoSuchElementException,
        TimeoutException,
        ElementClickInterceptedException,
    )
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False


class BilibiliBrowser:
    """
    Autonomous Bilibili video browser for AFK streaming.
    
    Opens Bilibili and automatically clicks through recommended videos
    to keep the stream engaging while the streamer is away.
    """

    # Video categories on Bilibili
    CATEGORIES = {
        "hot": "https://www.bilibili.com/v/popular/all",
        "gaming": "https://www.bilibili.com/v/game",
        "music": "https://www.bilibili.com/v/music",
        "dance": "https://www.bilibili.com/v/dance",
        "tech": "https://www.bilibili.com/v/tech",
        "life": "https://www.bilibili.com/v/life",
        "anime": "https://www.bilibili.com/v/anime",
        "entertainment": "https://www.bilibili.com/v/ent",
    }

    def __init__(
        self,
        browser: str = "edge",  # "chrome" or "edge"
        headless: bool = False,  # Set True if you don't want to see the browser
        video_duration_range: tuple[int, int] = (30, 120),  # Watch each video for 30-120 seconds
        start_category: str = "hot",
    ) -> None:
        if not SELENIUM_AVAILABLE:
            raise ImportError(
                "selenium is required for browser automation. "
                "Install with: pip install selenium"
            )
        
        self._browser_type = browser
        self._headless = headless
        self._video_duration_range = video_duration_range
        self._start_category = start_category
        self._driver: Optional[webdriver.Chrome | webdriver.Edge] = None
        self._running = False
        self._browse_task: Optional[threading.Thread] = None
        self._current_video_title = ""

    def _get_profile_dir(self) -> str:
        """Get (or create) a dedicated browser profile directory for XiaoTang."""
        profile_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", ".browser_profile")
        )
        os.makedirs(profile_dir, exist_ok=True)
        return profile_dir

    def _create_driver(self):
        """Create and configure the browser driver with a dedicated profile."""
        profile_dir = self._get_profile_dir()
        
        if self._browser_type == "chrome":
            options = ChromeOptions()
            if self._headless:
                options.add_argument("--headless")
            # Dedicated profile - persists login across runs, no conflict with main browser
            options.add_argument(f"--user-data-dir={profile_dir}")
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_argument("--autoplay-policy=no-user-gesture-required")
            options.add_argument("--log-level=3")  # Suppress console error spam
            options.add_argument("--disable-logging")
            options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
            options.add_experimental_option("useAutomationExtension", False)
            return webdriver.Chrome(options=options)
        else:  # edge
            options = EdgeOptions()
            if self._headless:
                options.add_argument("--headless")
            # Dedicated profile - persists login across runs, no conflict with main browser
            options.add_argument(f"--user-data-dir={profile_dir}")
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_argument("--autoplay-policy=no-user-gesture-required")
            options.add_argument("--log-level=3")  # Suppress console error spam
            options.add_argument("--disable-logging")
            options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
            options.add_experimental_option("useAutomationExtension", False)
            return webdriver.Edge(options=options)

    def start(self) -> None:
        """Start the browser."""
        if self._driver:
            return
        
        print(f"[browser] Starting {self._browser_type} browser...")
        self._driver = self._create_driver()
        self._driver.maximize_window()
        self._running = True
        
        # Navigate to starting category
        start_url = self.CATEGORIES.get(self._start_category, self.CATEGORIES["hot"])
        self._driver.get(start_url)
        print(f"[browser] Opened Bilibili: {self._start_category}")

    def stop(self) -> None:
        """Stop the browser."""
        self._running = False
        
        # Wait for browse task to finish (with timeout)
        if self._browse_task and self._browse_task.is_alive():
            self._browse_task.join(timeout=5.0)
            self._browse_task = None
        
        if self._driver:
            try:
                self._driver.quit()
            except Exception:
                pass
            self._driver = None
        
        print("[browser] Browser closed")

    def browse_loop(self) -> None:
        """Main browsing loop - continuously watch and switch videos."""
        if not self._driver:
            self.start()
        
        while self._running:
            try:
                # Click on a video if on category page
                if not self._is_watching_video():
                    self._click_random_video()
                
                # Wait for the video to finish (or use fallback duration)
                self._wait_for_video_end()
                
                if self._running:
                    # Click on a recommended video
                    self._click_recommended_video()
                    
            except Exception as e:
                print(f"[browser_error] {e}")
                time.sleep(5)
                # Try to recover by going back to category
                try:
                    start_url = self.CATEGORIES.get(self._start_category, self.CATEGORIES["hot"])
                    self._driver.get(start_url)
                except Exception:
                    pass

    def _get_video_duration(self) -> Optional[float]:
        """Get the total duration of the current video in seconds from Bilibili player."""
        try:
            # Bilibili uses bpx-player; try multiple ways to get duration
            duration = self._driver.execute_script("""
                // Method 1: HTML5 video element
                var video = document.querySelector('video');
                if (video && video.duration && !isNaN(video.duration) && video.duration > 0) {
                    return video.duration;
                }
                // Method 2: bpx player duration text (format: MM:SS or HH:MM:SS)
                var durEl = document.querySelector('.bpx-player-ctrl-time-duration');
                if (durEl) {
                    var parts = durEl.textContent.trim().split(':').map(Number);
                    if (parts.length === 2) return parts[0] * 60 + parts[1];
                    if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
                }
                return null;
            """)
            return float(duration) if duration else None
        except Exception:
            return None

    def _get_video_current_time(self) -> Optional[float]:
        """Get current playback position in seconds."""
        try:
            current = self._driver.execute_script("""
                var video = document.querySelector('video');
                if (video && !isNaN(video.currentTime)) return video.currentTime;
                return null;
            """)
            return float(current) if current is not None else None
        except Exception:
            return None

    def _wait_for_video_end(self) -> None:
        """Wait until the current video actually finishes playing."""
        if not self._is_watching_video():
            return
        
        # Give the player time to load
        time.sleep(5)
        
        # Only skip actual live streams (URL contains /live/ or duration is Infinity)
        try:
            url = self._driver.current_url
            if "/live/" in url:
                print("[browser] On a live stream page, skipping...")
                return
            is_infinite = self._driver.execute_script("""
                var video = document.querySelector('video');
                return video && !isFinite(video.duration);
            """)
            if is_infinite:
                print("[browser] Live stream detected (infinite duration), skipping...")
                return
        except Exception:
            pass
        
        duration = self._get_video_duration()
        if duration:
            print(f"[browser] Video duration: {int(duration)}s - watching until it ends")
        else:
            print("[browser] Watching video until it ends...")
        
        # Poll until the video ends (check .ended property or currentTime >= duration)
        while self._running:
            try:
                ended = self._driver.execute_script("""
                    var video = document.querySelector('video');
                    if (!video) return true;
                    if (video.ended) return true;
                    if (video.paused && video.currentTime > 0 && video.duration - video.currentTime < 2) return true;
                    return false;
                """)
                if ended:
                    print("[browser] Video finished!")
                    break
            except Exception:
                break
            time.sleep(3)

    def _is_watching_video(self) -> bool:
        """Check if currently on a video page."""
        try:
            current_url = self._driver.current_url
            return "/video/" in current_url or "/BV" in current_url
        except Exception:
            return False

    def _click_random_video(self) -> None:
        """Click on a random video from the current page."""
        try:
            time.sleep(3)  # Wait for page load
            
            # Scroll down a bit to get past header area
            self._driver.execute_script("window.scrollBy(0, 300);")
            time.sleep(0.5)
            
            # Find video links directly
            links = self._driver.find_elements(By.CSS_SELECTOR, "a[href*='/video/BV']")
            
            if links:
                # Filter to visible ones
                visible = [l for l in links if l.is_displayed()]
                if visible:
                    link = random.choice(visible[:15])
                    
                    # Get title
                    try:
                        self._current_video_title = link.text[:50] if link.text else "Unknown"
                    except Exception:
                        self._current_video_title = "Unknown"
                    
                    # Get href and navigate directly (avoids click interception)
                    href = link.get_attribute("href")
                    if href:
                        if href.startswith("//"):
                            href = "https:" + href
                        print(f"[browser] Opening video: {self._current_video_title}")
                        self._driver.get(href)
                        time.sleep(3)
                        return
            
            print("[browser] No videos found on page")
                    
        except Exception as e:
            print(f"[browser] Failed to click video: {e}")

    def _click_recommended_video(self) -> None:
        """Click on a recommended video from the sidebar."""
        try:
            time.sleep(1)
            
            # Find all video links on the page (recommendations)
            links = self._driver.find_elements(By.CSS_SELECTOR, "a[href*='/video/BV']")
            
            if links:
                # Filter to visible and not the current video
                current_url = self._driver.current_url
                visible = [
                    l for l in links 
                    if l.is_displayed() and l.get_attribute("href") != current_url
                ]
                
                if visible:
                    rec = random.choice(visible[:8])
                    
                    # Get title
                    try:
                        self._current_video_title = rec.text[:50] if rec.text else "Unknown"
                    except Exception:
                        self._current_video_title = "Unknown"
                    
                    # Navigate directly via href
                    href = rec.get_attribute("href")
                    if href:
                        if href.startswith("//"):
                            href = "https:" + href
                        print(f"[browser] Next video: {self._current_video_title}")
                        self._driver.get(href)
                        time.sleep(3)
                        return
            
            # Fallback: go back to category page
            print("[browser] No recommendations found, returning to category...")
            start_url = self.CATEGORIES.get(self._start_category, self.CATEGORIES["hot"])
            self._driver.get(start_url)
            
        except Exception as e:
            print(f"[browser] Failed to click recommendation: {e}")
            # Go back to category
            try:
                start_url = self.CATEGORIES.get(self._start_category, self.CATEGORIES["hot"])
                self._driver.get(start_url)
            except Exception:
                pass

    def start_browsing(self) -> None:
        """Start the browsing loop in a background thread."""
        if self._browse_task and self._browse_task.is_alive():
            return
        self._running = True
        self._browse_task = threading.Thread(target=self.browse_loop, daemon=True)
        self._browse_task.start()
        print("[browser] Started browsing task")

    def go_to_category(self, category: str) -> None:
        """Navigate to a specific category."""
        if not self._driver:
            return
        
        url = self.CATEGORIES.get(category, self.CATEGORIES["hot"])
        self._driver.get(url)
        print(f"[browser] Switched to category: {category}")

    def go_to_video(self, bv_id: str) -> None:
        """Navigate to a specific video by BV ID."""
        if not self._driver:
            return
        
        url = f"https://www.bilibili.com/video/{bv_id}"
        self._driver.get(url)
        print(f"[browser] Opened video: {bv_id}")

    @property
    def current_video(self) -> str:
        return self._current_video_title

    @property
    def is_running(self) -> bool:
        return self._running


def is_selenium_available() -> bool:
    """Check if selenium is installed."""
    return SELENIUM_AVAILABLE


if __name__ == "__main__":
    """Standalone demo - browse Bilibili until Ctrl+C."""
    if not SELENIUM_AVAILABLE:
        print("Selenium not installed. Run: pip install selenium")
        exit(1)
    
    print("Starting Bilibili browser...")
    print("Press Ctrl+C to stop\n")
    
    browser = BilibiliBrowser(
        browser="edge",
        headless=False,
        video_duration_range=(60, 600),
        start_category="hot",
    )
    
    try:
        browser.start()
        browser.start_browsing()
        
        # Run indefinitely until Ctrl+C
        while browser.is_running:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        browser.stop()
