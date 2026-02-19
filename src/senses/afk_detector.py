"""AFK Detector - Monitor keyboard/mouse activity to detect when streamer is away."""

from __future__ import annotations

import asyncio
import time
from typing import Callable, Optional

try:
    from pynput import mouse, keyboard
    PYNPUT_AVAILABLE = True
except ImportError:
    PYNPUT_AVAILABLE = False


class AFKDetector:
    """
    Detects when the user is AFK (away from keyboard) based on input activity.
    
    When no keyboard/mouse activity is detected for the timeout period,
    the user is considered AFK and XiaoTang should take over.
    """

    def __init__(
        self,
        timeout_seconds: float = 60.0,
        on_afk_start: Optional[Callable] = None,
        on_afk_end: Optional[Callable] = None,
    ) -> None:
        """
        Args:
            timeout_seconds: Seconds of inactivity before considered AFK
            on_afk_start: Callback when user goes AFK
            on_afk_end: Callback when user returns from AFK
        """
        if not PYNPUT_AVAILABLE:
            raise ImportError(
                "pynput is required for AFK detection. "
                "Install with: pip install pynput"
            )
        
        self._timeout = timeout_seconds
        self._last_activity = time.time()
        self._is_afk = False
        self._running = False
        self._on_afk_start = on_afk_start
        self._on_afk_end = on_afk_end
        
        self._mouse_listener: Optional[mouse.Listener] = None
        self._keyboard_listener: Optional[keyboard.Listener] = None
        self._monitor_task: Optional[asyncio.Task] = None

    def _on_activity(self, *args) -> None:
        """Called on any keyboard/mouse activity."""
        self._last_activity = time.time()
        
        # If was AFK and now active, trigger callback
        if self._is_afk:
            self._is_afk = False
            print("[afk] User returned - XiaoTang going quiet")
            if self._on_afk_end:
                self._on_afk_end()

    def start(self) -> None:
        """Start monitoring for activity."""
        self._running = True
        self._last_activity = time.time()
        
        # Start mouse listener
        self._mouse_listener = mouse.Listener(
            on_move=self._on_activity,
            on_click=self._on_activity,
            on_scroll=self._on_activity,
        )
        self._mouse_listener.start()
        
        # Start keyboard listener
        self._keyboard_listener = keyboard.Listener(
            on_press=self._on_activity,
            on_release=self._on_activity,
        )
        self._keyboard_listener.start()
        
        print(f"[afk] Activity monitoring started (timeout: {self._timeout}s)")

    def stop(self) -> None:
        """Stop monitoring."""
        self._running = False
        
        if self._mouse_listener:
            self._mouse_listener.stop()
            self._mouse_listener = None
        
        if self._keyboard_listener:
            self._keyboard_listener.stop()
            self._keyboard_listener = None
        
        if self._monitor_task:
            self._monitor_task.cancel()
            self._monitor_task = None
        
        print("[afk] Activity monitoring stopped")

    async def monitor_loop(self) -> None:
        """Async loop to check AFK status periodically."""
        while self._running:
            await asyncio.sleep(5)  # Check every 5 seconds
            
            idle_time = time.time() - self._last_activity
            
            if not self._is_afk and idle_time >= self._timeout:
                self._is_afk = True
                print(f"[afk] User AFK for {idle_time:.0f}s - XiaoTang activated!")
                if self._on_afk_start:
                    self._on_afk_start()

    def start_async_monitor(self) -> asyncio.Task:
        """Start the async monitoring loop."""
        self._monitor_task = asyncio.create_task(self.monitor_loop())
        return self._monitor_task

    @property
    def is_afk(self) -> bool:
        """Check if user is currently AFK."""
        if not self._running:
            return True  # If not monitoring, assume AFK (bot always on)
        
        idle_time = time.time() - self._last_activity
        return idle_time >= self._timeout

    @property
    def idle_seconds(self) -> float:
        """Get seconds since last activity."""
        return time.time() - self._last_activity

    @property
    def is_running(self) -> bool:
        return self._running


def is_pynput_available() -> bool:
    """Check if pynput is installed."""
    return PYNPUT_AVAILABLE
