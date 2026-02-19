"""
XiaoTang AI Companion - Main Entry Point

A modular AI streaming companion with:
- Brain: LLM reasoning and decision making
- Voice: Text-to-speech output
- Vision: Screen reading (future)
- Hands: Computer control (future)
- Memory: Semantic knowledge storage
- Senses: Chat/danmaku input
- Overlay: OBS subtitle display
"""

from __future__ import annotations

import asyncio
import sys
import time
from collections import deque
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from brain import LLMClient, is_message_allowed, is_low_value_message
from brain.llm_client import build_messages
from brain.policy import detect_language
from voice import TTSEngine
from memory import MemoryClient
from memory.store import load_memory_lines, select_memory
from senses import DanmakuListener
from senses.afk_detector import AFKDetector, is_pynput_available
from overlay import OverlayServer
from config import load_settings


class XiaoTang:
    """
    XiaoTang AI Streaming Companion - Main orchestrator.
    
    Coordinates all modules to create an autonomous AI streamer assistant.
    """

    def __init__(self) -> None:
        self.settings = load_settings()
        
        # Initialize modules
        self.llm = LLMClient(
            api_key=self.settings.openai_api_key,
            model=self.settings.openai_model,
            base_url=self.settings.openai_base_url,
        )
        self.voice = TTSEngine()
        self.memory = MemoryClient(knowledge_dir="src/memory/knowledge")
        self.overlay = OverlayServer(port=8765)
        self.danmaku = DanmakuListener(
            room_id=self.settings.room_id,
            sessdata=self.settings.sessdata,
            bili_jct=self.settings.bili_jct,
            buvid3=self.settings.buvid3,
        )
        
        # AFK detector (only if enabled and pynput available)
        self.afk_detector = None
        if self.settings.afk_mode:
            if is_pynput_available():
                self.afk_detector = AFKDetector(
                    timeout_seconds=self.settings.afk_timeout_minutes * 60,
                    on_afk_start=self._on_afk_start,
                    on_afk_end=self._on_afk_end,
                )
            else:
                print("[warning] AFK_MODE enabled but pynput not installed. Run: pip install pynput")
        
        # State
        self._recent_messages: deque[str] = deque(maxlen=50)
        self._last_response_at = 0.0
        self._response_lock = asyncio.Lock()
        self._welcomed_viewers: set[int] = set()  # Track welcomed UIDs
        self._last_welcome_at = 0.0
        self._welcome_cooldown = 3.0  # Seconds between welcomes
        
        # Legacy memory lines for backward compatibility
        self._memory_lines = load_memory_lines(self.settings.memory_path)

    async def start(self) -> None:
        """Start all XiaoTang services."""
        print("[xiaotang] Starting XiaoTang AI Companion...")
        
        # Start AFK detector if enabled
        if self.afk_detector:
            self.afk_detector.start()
            self.afk_detector.start_async_monitor()
            print(f"[xiaotang] AFK mode: XiaoTang activates after {self.settings.afk_timeout_minutes} min idle")
        else:
            print("[xiaotang] AFK mode: OFF (always active)")
        
        # Start overlay server
        await self.overlay.start()
        print("[xiaotang] OBS Overlay: http://127.0.0.1:8765/")
        
        # Register danmaku handler
        self.danmaku.on("danmaku", self._handle_danmaku)
        self.danmaku.on("viewer_enter", self._handle_viewer_enter)
        self.danmaku.on("live_start", self._on_live_start)
        self.danmaku.on("live_end", self._on_live_end)
        
        print(f"[xiaotang] Connecting to Bilibili room {self.settings.room_id}...")
        print("[xiaotang] TTS enabled - XiaoTang will speak responses!")
        
        try:
            await self.danmaku.start()
        except KeyboardInterrupt:
            pass
        finally:
            await self.stop()

    async def stop(self) -> None:
        """Stop all services."""
        print("[xiaotang] Shutting down...")
        if self.afk_detector:
            self.afk_detector.stop()
        await self.danmaku.stop()
        await self.overlay.stop()
        self.voice.cleanup()

    def _on_afk_start(self) -> None:
        """Called when user goes AFK - XiaoTang activates."""
        pass  # Could add announcement here

    def _on_afk_end(self) -> None:
        """Called when user returns - XiaoTang goes quiet."""
        pass  # Could add announcement here

    def _is_active(self) -> bool:
        """Check if XiaoTang should be active (responding to messages)."""
        # If AFK mode is disabled, always active
        if not self.afk_detector:
            return True
        # If AFK mode enabled, only active when user is AFK
        return self.afk_detector.is_afk

    async def _handle_danmaku(self, msg: dict) -> None:
        """Handle incoming danmaku message."""
        text = msg.get("text", "")
        username = msg.get("username", "unknown")
        
        if not text:
            return
        
        print(f"[danmaku] {username}: {text}")
        self._recent_messages.append(f"{username}: {text}")
        
        # Check if we should respond
        if not self._should_respond(text):
            return
        
        async with self._response_lock:
            # Double check after acquiring lock
            if not self._should_respond(text):
                return
            
            # Generate response
            reply = await self._generate_reply(username, text)
            if not reply:
                return
            
            self._last_response_at = time.time()
            print(f"[xiaotang] {reply}")
            
            # Record in memory
            self.memory.add_to_conversation("user", text, username)
            self.memory.add_to_conversation("assistant", reply)
            
            # Output to overlay
            try:
                await self.overlay.broadcast(username, text, reply)
            except Exception as e:
                print(f"[overlay_error] {e}")
            
            # Speak the reply
            language = detect_language(text)
            try:
                await self.voice.speak(reply, language)
            except Exception as e:
                print(f"[tts_error] {e}")

    def _should_respond(self, text: str) -> bool:
        """Determine if XiaoTang should respond to this message."""
        # Check if XiaoTang is active (AFK mode check)
        if not self._is_active():
            return False
        if not is_message_allowed(text):
            return False
        if is_low_value_message(text):
            return False
        if time.time() - self._last_response_at < self.settings.response_cooldown_sec:
            return False
        return True

    async def _generate_reply(self, username: str, text: str) -> str | None:
        """Generate a reply using the LLM."""
        language = detect_language(text)
        
        # Get relevant memories
        memory_hits = select_memory(self._memory_lines, text)
        recent_highlights = list(self._recent_messages)[-self.settings.max_context_messages:]
        
        persona = "Cute, witty, supportive, and brief."
        
        messages = build_messages(
            persona=persona,
            language=language,
            memory_lines=memory_hits,
            recent_messages=recent_highlights,
            user_message=text,
        )
        
        try:
            return self.llm.generate(messages)
        except Exception as e:
            print(f"[llm_error] {e}")
            return None

    async def _on_live_start(self, event: dict) -> None:
        """Handle stream start event."""
        print("[event] Stream started!")

    async def _on_live_end(self, event: dict) -> None:
        """Handle stream end event."""
        print("[event] Stream ended / preparing...")

    async def _handle_viewer_enter(self, viewer: dict) -> None:
        """Handle viewer enter event (pre-parsed from danmaku listener)."""
        if not self.settings.welcome_new_viewers:
            return
        
        # Check if XiaoTang is active (AFK mode check)
        if not self._is_active():
            return
        
        # Only welcome on room entry (msg_type=1)
        if viewer.get("type") != 1:
            return
        
        uid = viewer.get("uid", 0)
        username = viewer.get("username", "unknown")
        
        if not uid or uid in self._welcomed_viewers:
            return
        
        # Cooldown check
        if time.time() - self._last_welcome_at < self._welcome_cooldown:
            return
        
        self._welcomed_viewers.add(uid)
        self._last_welcome_at = time.time()
        
        # Keep set bounded (remove oldest if too large)
        if len(self._welcomed_viewers) > 500:
            self._welcomed_viewers.clear()
        
        print(f"[interact] New viewer: {username} (uid: {uid})")
        
        # Generate welcome message
        await self._welcome_viewer(username)

    async def _welcome_viewer(self, username: str) -> None:
        """Generate and speak a welcome message for a new viewer."""
        language = self.settings.default_language
        
        # Generate a short welcome using LLM
        messages = [
            {
                "role": "system",
                "content": (
                    "You are XiaoTang (小糖), a sassy and playful AI streaming companion. "
                    "When a new viewer enters, welcome them by NAME and make a witty, playful roast about their username. "
                    "Be cheeky but not mean - the goal is to make them laugh and engage. "
                    "Examples of good roasts: '哎呀 [爱吃键盘的大唐] 来了！键盘好吃吗？薄膜的还是机械的？' "
                    "or '欢迎 [某某某]！这名字起的...你爸妈知道吗？哈哈开玩笑的~' "
                    "Keep it under 25 words. Must include their actual username. "
                    f"Reply in {language}."
                ),
            },
            {
                "role": "user",
                "content": f"New viewer just entered: {username}",
            },
        ]
        
        try:
            welcome_msg = self.llm.generate(messages, max_tokens=50)
            print(f"[xiaotang] (welcome) {welcome_msg}")
            
            # Show on overlay
            await self.overlay.broadcast(username, "进入直播间", welcome_msg)
            
            # Speak
            await self.voice.speak(welcome_msg, language)
        except Exception as e:
            print(f"[welcome_error] {e}")


async def main() -> None:
    """Main entry point."""
    xiaotang = XiaoTang()
    await xiaotang.start()


if __name__ == "__main__":
    asyncio.run(main())
