from __future__ import annotations

import asyncio
from collections import deque
import time
import re

from bilibili_api import live, Credential

from config import load_settings
from llm_client import build_messages, generate_reply
from memory_store import load_memory_lines, select_memory
from policy import is_message_allowed, is_low_value_message
from tts_engine import TTSEngine


_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def detect_language(message: str) -> str:
    return "Chinese" if _CJK_RE.search(message) else "English"


def should_respond(message: str, last_response_at: float, cooldown_sec: float) -> bool:
    if not is_message_allowed(message):
        return False
    if is_low_value_message(message):
        return False
    if time.time() - last_response_at < cooldown_sec:
        return False

    # Respond to all valid messages like a streamer
    return True


class XiaoTangDanmakuListener:
    def __init__(
        self,
        settings,
        memory_lines: list[str],
        tts: TTSEngine,
    ) -> None:
        self._settings = settings
        self._memory_lines = memory_lines
        self._tts = tts
        self._recent_messages: deque[str] = deque(maxlen=50)
        self._response_lock = asyncio.Lock()
        self._last_response_at = 0.0

    async def handle_danmaku(self, event: dict) -> None:
        """Handle a DANMU_MSG event."""
        data = event.get("data", {})
        info = data.get("info", [])

        # Extract message text
        try:
            text = str(info[1]) if len(info) > 1 else ""
        except (IndexError, TypeError):
            text = ""

        # Extract username
        try:
            user_info = info[2] if len(info) > 2 else []
            if isinstance(user_info, list) and len(user_info) > 1:
                username = str(user_info[1])
            else:
                username = "unknown"
        except (IndexError, TypeError):
            username = "unknown"

        if not text:
            return

        print(f"[danmaku] {username}: {text}")

        self._recent_messages.append(f"{username}: {text}")
        if not should_respond(text, self._last_response_at, self._settings.response_cooldown_sec):
            return

        async with self._response_lock:
            if not should_respond(text, self._last_response_at, self._settings.response_cooldown_sec):
                return

            language = detect_language(text)
            memory_hits = select_memory(self._memory_lines, text)
            recent_highlights = list(self._recent_messages)[-self._settings.max_context_messages:]
            persona = "Cute, witty, supportive, and brief."

            messages = build_messages(
                persona=persona,
                language=language,
                memory_lines=memory_hits,
                recent_messages=recent_highlights,
                user_message=text,
            )

            try:
                reply = generate_reply(
                    api_key=self._settings.openai_api_key,
                    model=self._settings.openai_model,
                    messages=messages,
                    base_url=self._settings.openai_base_url,
                )
            except Exception as exc:  # noqa: BLE001
                print(f"[llm_error] {exc}")
                return

            self._last_response_at = time.time()
            print(f"[xiaotang] {reply}")

            # Speak the reply
            try:
                await self._tts.speak(reply, language)
            except Exception as exc:  # noqa: BLE001
                print(f"[tts_error] {exc}")


async def main() -> None:
    settings = load_settings()
    memory_lines = load_memory_lines(settings.memory_path)

    # Initialize TTS engine
    tts = TTSEngine()

    # Create credential from cookies
    credential = Credential(
        sessdata=settings.sessdata,
        bili_jct=settings.bili_jct,
        buvid3=settings.buvid3,
    )

    print(f"[debug] Credential created with sessdata={bool(settings.sessdata)}, bili_jct={bool(settings.bili_jct)}, buvid3={bool(settings.buvid3)}")

    # Create the live danmaku client
    room = live.LiveDanmaku(settings.room_id, credential=credential)

    # Create our handler
    listener = XiaoTangDanmakuListener(settings, memory_lines, tts)

    @room.on("DANMU_MSG")
    async def on_danmaku(event: dict) -> None:
        await listener.handle_danmaku(event)

    @room.on("LIVE")
    async def on_live(event: dict) -> None:
        print("[event] Stream started!")

    @room.on("PREPARING")
    async def on_preparing(event: dict) -> None:
        print("[event] Stream ended / preparing...")

    print(f"[xiaotang] Listening on Bilibili room {settings.room_id}...")
    print("[xiaotang] TTS enabled - XiaoTang will speak responses!")
    try:
        await room.connect()
    except KeyboardInterrupt:
        print("[xiaotang] Shutting down...")
    finally:
        await room.disconnect()
        tts.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
