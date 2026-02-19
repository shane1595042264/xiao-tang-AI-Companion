"""Danmaku Listener - Bilibili live chat integration."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Any, Callable, Optional

from bilibili_api import live, Credential


class DanmakuListener:
    """
    Listens to Bilibili live room danmaku (chat messages).
    
    This is XiaoTang's "ears" for the streaming platform.
    """

    def __init__(
        self,
        room_id: int,
        sessdata: str = "",
        bili_jct: str = "",
        buvid3: str = "",
    ) -> None:
        self._room_id = room_id
        self._credential = Credential(
            sessdata=sessdata,
            bili_jct=bili_jct,
            buvid3=buvid3,
        )
        self._room: Optional[live.LiveDanmaku] = None
        self._handlers: dict[str, list[Callable]] = {}
        self._message_history: deque[dict] = deque(maxlen=100)
        self._running = False

    def on(self, event_type: str, handler: Callable) -> None:
        """Register an event handler."""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    async def _dispatch(self, event_type: str, event: dict) -> None:
        """Dispatch an event to all registered handlers."""
        for handler in self._handlers.get(event_type, []):
            try:
                result = handler(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                print(f"[danmaku_error] Handler error: {e}")

    async def start(self) -> None:
        """Start listening to the room."""
        self._room = live.LiveDanmaku(self._room_id, credential=self._credential)
        self._running = True

        @self._room.on("DANMU_MSG")
        async def on_danmaku(event: dict) -> None:
            parsed = self._parse_danmaku(event)
            if parsed:
                self._message_history.append(parsed)
                await self._dispatch("danmaku", parsed)
                await self._dispatch("DANMU_MSG", event)

        @self._room.on("LIVE")
        async def on_live(event: dict) -> None:
            await self._dispatch("live_start", event)

        @self._room.on("PREPARING")
        async def on_preparing(event: dict) -> None:
            await self._dispatch("live_end", event)

        @self._room.on("SUPER_CHAT_MESSAGE")
        async def on_superchat(event: dict) -> None:
            await self._dispatch("superchat", event)

        @self._room.on("SEND_GIFT")
        async def on_gift(event: dict) -> None:
            await self._dispatch("gift", event)

        @self._room.on("INTERACT_WORD")
        async def on_interact(event: dict) -> None:
            await self._dispatch("interact", event)
            parsed = self._parse_interact(event)
            if parsed:
                await self._dispatch("viewer_enter", parsed)

        @self._room.on("INTERACT_WORD_V2")
        async def on_interact_v2(event: dict) -> None:
            parsed = self._parse_interact_v2(event)
            if parsed:
                await self._dispatch("interact", event)
                await self._dispatch("viewer_enter", parsed)

        print(f"[danmaku] Connecting to room {self._room_id}...")
        await self._room.connect()

    async def stop(self) -> None:
        """Stop listening."""
        self._running = False
        if self._room:
            await self._room.disconnect()

    def _parse_danmaku(self, event: dict) -> Optional[dict]:
        """Parse a DANMU_MSG event into a clean format."""
        data = event.get("data", {})
        info = data.get("info", [])

        try:
            text = str(info[1]) if len(info) > 1 else ""
            user_info = info[2] if len(info) > 2 else []
            
            if isinstance(user_info, list) and len(user_info) > 1:
                username = str(user_info[1])
                uid = int(user_info[0]) if user_info[0] else 0
            else:
                username = "unknown"
                uid = 0

            medal_info = info[3] if len(info) > 3 else []
            medal_name = medal_info[1] if isinstance(medal_info, list) and len(medal_info) > 1 else ""
            medal_level = medal_info[0] if isinstance(medal_info, list) and medal_info else 0

            return {
                "text": text,
                "username": username,
                "uid": uid,
                "medal_name": medal_name,
                "medal_level": medal_level,
                "timestamp": time.time(),
                "raw": event,
            }
        except (IndexError, TypeError, ValueError):
            return None

    def get_recent_messages(self, n: int = 20) -> list[dict]:
        """Get recent messages."""
        return list(self._message_history)[-n:]

    def _parse_interact(self, event: dict) -> Optional[dict]:
        """Parse an INTERACT_WORD event."""
        try:
            data = event.get("data", {})
            interact_data = data.get("data", {})
            
            msg_type = interact_data.get("msg_type", 0)
            # msg_type: 1=enter, 2=follow, 3=share, 4=special follow, 5=mutual follow
            
            return {
                "type": msg_type,
                "type_name": {1: "enter", 2: "follow", 3: "share"}.get(msg_type, "unknown"),
                "uid": interact_data.get("uid", 0),
                "username": interact_data.get("uname", "unknown"),
                "timestamp": time.time(),
                "raw": event,
            }
        except (KeyError, TypeError):
            return None

    def _parse_interact_v2(self, event: dict) -> Optional[dict]:
        """Parse an INTERACT_WORD_V2 event (newer format with pb_decoded)."""
        try:
            data = event.get("data", {})
            inner_data = data.get("data", {})
            pb_decoded = inner_data.get("pb_decoded", {})
            
            if not pb_decoded:
                return None
            
            msg_type = pb_decoded.get("msg_type", 0)
            # msg_type: 1=enter, 2=follow, 3=share
            
            return {
                "type": msg_type,
                "type_name": {1: "enter", 2: "follow", 3: "share"}.get(msg_type, "unknown"),
                "uid": pb_decoded.get("uid", 0),
                "username": pb_decoded.get("uname", "unknown"),
                "timestamp": time.time(),
                "raw": event,
            }
        except (KeyError, TypeError):
            return None

    @property
    def room_id(self) -> int:
        return self._room_id

    @property
    def is_running(self) -> bool:
        return self._running
