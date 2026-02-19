"""System Control - Low-level computer interaction (keyboard, mouse, clipboard)."""

from __future__ import annotations

import asyncio
from typing import Optional, Tuple


class SystemControl:
    """
    Low-level system control for autonomous computer operation.
    
    Provides keyboard, mouse, and clipboard control.
    Requires pyautogui or pynput for full functionality.
    """

    def __init__(self) -> None:
        self._enabled = False
        self._safety_pause = 0.1  # Seconds between actions

    async def type_text(self, text: str, interval: float = 0.05) -> dict:
        """
        Type text using the keyboard.
        
        Args:
            text: Text to type
            interval: Seconds between keystrokes
        """
        try:
            import pyautogui
            pyautogui.typewrite(text, interval=interval)
            return {"status": "typed", "text": text[:50]}
        except ImportError:
            return {"status": "error", "error": "pyautogui not installed"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def press_key(self, key: str) -> dict:
        """Press a single key or key combination."""
        try:
            import pyautogui
            if "+" in key:
                keys = key.split("+")
                pyautogui.hotkey(*keys)
            else:
                pyautogui.press(key)
            return {"status": "pressed", "key": key}
        except ImportError:
            return {"status": "error", "error": "pyautogui not installed"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def move_mouse(self, x: int, y: int, duration: float = 0.5) -> dict:
        """Move the mouse to a specific position."""
        try:
            import pyautogui
            pyautogui.moveTo(x, y, duration=duration)
            return {"status": "moved", "position": (x, y)}
        except ImportError:
            return {"status": "error", "error": "pyautogui not installed"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def click(
        self,
        x: Optional[int] = None,
        y: Optional[int] = None,
        button: str = "left",
        clicks: int = 1,
    ) -> dict:
        """Click the mouse."""
        try:
            import pyautogui
            if x is not None and y is not None:
                pyautogui.click(x, y, button=button, clicks=clicks)
            else:
                pyautogui.click(button=button, clicks=clicks)
            return {"status": "clicked", "button": button, "clicks": clicks}
        except ImportError:
            return {"status": "error", "error": "pyautogui not installed"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def scroll(self, amount: int) -> dict:
        """Scroll the mouse wheel."""
        try:
            import pyautogui
            pyautogui.scroll(amount)
            return {"status": "scrolled", "amount": amount}
        except ImportError:
            return {"status": "error", "error": "pyautogui not installed"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def get_clipboard(self) -> str:
        """Get text from clipboard."""
        try:
            import pyperclip
            return pyperclip.paste()
        except ImportError:
            return ""

    async def set_clipboard(self, text: str) -> dict:
        """Set text to clipboard."""
        try:
            import pyperclip
            pyperclip.copy(text)
            return {"status": "copied", "length": len(text)}
        except ImportError:
            return {"status": "error", "error": "pyperclip not installed"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def get_mouse_position(self) -> Tuple[int, int]:
        """Get current mouse position."""
        try:
            import pyautogui
            return pyautogui.position()
        except ImportError:
            return (0, 0)

    async def screenshot_region(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
    ) -> bytes:
        """Take a screenshot of a specific region."""
        try:
            import pyautogui
            import io
            screenshot = pyautogui.screenshot(region=(x, y, width, height))
            buffer = io.BytesIO()
            screenshot.save(buffer, format="PNG")
            return buffer.getvalue()
        except ImportError:
            raise RuntimeError("pyautogui not installed")
