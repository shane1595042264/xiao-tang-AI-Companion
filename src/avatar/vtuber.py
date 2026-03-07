"""VTuber Controller - Live2D avatar control via VTube Studio API."""

from __future__ import annotations

import asyncio
from typing import Optional

try:
    import pyvts
    PYVTS_AVAILABLE = True
except ImportError:
    PYVTS_AVAILABLE = False


def is_vtuber_available() -> bool:
    """Check if pyvts is installed."""
    return PYVTS_AVAILABLE


class VTuberController:
    """Controls a Live2D avatar in VTube Studio via pyvts.

    Handles expressions only — lip sync is handled natively by VTube Studio
    via virtual audio cable from the TTS engine.
    """

    DEFAULT_EXPRESSIONS = {
        "happy": "xingxingyan",
        "excited": "xingxingyan",
        "angry": "shengqi",
        "roast": "wuyu",
        "sad": "shangxin",
        "cry": "kuqi",
        "confused": "chidai",
        "speechless": "wuyu",
        "gesture": "shoushi",
        "neutral": None,
    }

    def __init__(
        self,
        port: int = 8001,
        expressions: dict[str, str] | None = None,
    ) -> None:
        if not PYVTS_AVAILABLE:
            raise ImportError("pyvts is required. Install with: pip install pyvts")

        self._port = port
        self._expressions = expressions or self.DEFAULT_EXPRESSIONS
        self._vts: Optional[pyvts.vts] = None
        self._connected = False
        self._active_expression: str | None = None
        self._hotkey_cache: dict[str, str] = {}

    async def connect(self) -> bool:
        """Connect to VTube Studio and authenticate."""
        try:
            plugin_info = {
                "plugin_name": "XiaoTang AI Companion",
                "developer": "douvle",
                "authentication_token_path": "./vts_token.txt",
            }
            self._vts = pyvts.vts(plugin_info=plugin_info)
            await self._vts.connect()
            await self._vts.request_authenticate_token()
            await self._vts.request_authenticate()
            self._connected = True
            await self._cache_hotkeys()
            print("[vtuber] Connected to VTube Studio")
            return True
        except Exception as e:
            print(f"[vtuber] Failed to connect: {e}")
            self._connected = False
            return False

    async def _cache_hotkeys(self) -> None:
        """Cache hotkey name -> ID mapping."""
        if not self._vts:
            return
        try:
            response = await self._vts.request(
                self._vts.vts_request.requestHotKeyList()
            )
            hotkeys = response.get("data", {}).get("availableHotkeys", [])
            self._hotkey_cache = {}
            for hk in hotkeys:
                name = hk.get("name", "").lower().strip()
                if name:
                    self._hotkey_cache[name] = hk["hotkeyID"]
            print(f"[vtuber] Hotkeys: {list(self._hotkey_cache.keys())}")
        except Exception as e:
            print(f"[vtuber] Failed to cache hotkeys: {e}")

    async def disconnect(self) -> None:
        """Disconnect from VTube Studio."""
        if self._vts:
            try:
                await self._vts.close()
            except Exception:
                pass
        self._connected = False
        print("[vtuber] Disconnected from VTube Studio")

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def set_expression(self, emotion: str) -> None:
        """Trigger an expression in VTube Studio."""
        if not self._connected or not self._vts:
            return

        expr_name = self._expressions.get(emotion)

        if expr_name is None:
            if self._active_expression:
                await self._trigger_hotkey(self._active_expression)
                self._active_expression = None
            return

        if expr_name == self._active_expression:
            return

        if self._active_expression:
            await self._trigger_hotkey(self._active_expression)

        if await self._trigger_hotkey(expr_name):
            self._active_expression = expr_name
            print(f"[vtuber] Expression: {emotion} ({expr_name})")

    async def _trigger_hotkey(self, name: str) -> bool:
        """Trigger a hotkey by name."""
        hotkey_id = self._hotkey_cache.get(name.lower())
        if not hotkey_id or not self._vts:
            return False
        try:
            await self._vts.request(
                self._vts.vts_request.requestTriggerHotKey(hotkey_id)
            )
            return True
        except Exception as e:
            print(f"[vtuber] Hotkey failed '{name}': {e}")
            return False
