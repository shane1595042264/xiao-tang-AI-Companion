"""
XiaoTang AI Companion - Main Entry Point

A modular AI streaming companion with:
- Brain: LLM reasoning and decision making
- Voice: Text-to-speech output
- Vision: OBS screen capture for visual context
- Hands: Computer control (future)
- Memory: Semantic knowledge storage
- Senses: Chat/danmaku input
- Overlay: OBS subtitle display
"""

from __future__ import annotations

import asyncio
import re
import sys
import threading
import time
from collections import deque
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from brain import LLMClient
from brain.llm_client import build_messages
from brain.policy import detect_language
from voice import TTSEngine
from memory import MemoryClient
from memory.store import load_memory_lines, select_memory
from senses import DanmakuListener
from senses.afk_detector import AFKDetector, is_pynput_available
from senses.voice_listener import VoiceListener, is_voice_listen_available
from hands.bilibili_browser import BilibiliBrowser, is_selenium_available
from vision import OBSVisionClient
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
            api_key=self.settings.anthropic_api_key,
            model=self.settings.anthropic_model,
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
        
        # Bilibili browser for AFK browsing
        self.bilibili_browser = None
        if self.settings.afk_browse_bilibili:
            if is_selenium_available():
                self.bilibili_browser = BilibiliBrowser(
                    browser="edge",
                    headless=False,
                    video_duration_range=(
                        self.settings.afk_video_duration_min,
                        self.settings.afk_video_duration_max,
                    ),
                    start_category=self.settings.afk_browse_category,
                )
            else:
                print("[warning] AFK_BROWSE_BILIBILI enabled but selenium not installed. Run: pip install selenium")

        # OBS Vision (optional — screenshots for visual context)
        self.obs_vision = None
        if self.settings.obs_vision_enabled:
            self.obs_vision = OBSVisionClient(
                host=self.settings.obs_host,
                port=self.settings.obs_port,
                password=self.settings.obs_password,
                width=self.settings.obs_screenshot_width,
                height=self.settings.obs_screenshot_height,
            )

        # Voice listener for "assistant mode" when user is at computer
        self.ears = None
        if self.settings.voice_listen_enabled:
            if is_voice_listen_available():
                if self.settings.groq_api_key:
                    self.ears = VoiceListener(
                        groq_api_key=self.settings.groq_api_key,
                        device_index=self.settings.voice_device_index,
                        vad_aggressiveness=self.settings.voice_vad_aggressiveness,
                    )
                else:
                    print("[warning] VOICE_LISTEN_ENABLED but GROQ_API_KEY not set")
            else:
                print("[warning] VOICE_LISTEN_ENABLED but dependencies missing. "
                      "Run: pip install sounddevice webrtcvad-wheels numpy httpx")

        # State
        self._recent_messages: deque[str] = deque(maxlen=50)
        self._message_queue: asyncio.Queue[dict] = asyncio.Queue()
        self._welcomed_viewers: set[int] = set()  # Track welcomed UIDs
        self._last_welcome_at = 0.0
        self._welcome_cooldown = 3.0  # Seconds between welcomes
        self._loop: asyncio.AbstractEventLoop | None = None

        # Voice/interruption state
        self._is_speaking = False
        self._current_tts_text = ""
        self._pending_interruption: str | None = None
        self._last_voice_input_at = 0.0

        # Load persona from knowledge folder
        self._persona = self._load_persona()

        # Legacy memory lines for backward compatibility
        self._memory_lines = load_memory_lines(self.settings.memory_path)

    async def start(self) -> None:
        """Start all XiaoTang services."""
        self._loop = asyncio.get_running_loop()
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

        # Connect to OBS for vision
        if self.obs_vision:
            if self.obs_vision.connect():
                scene = self.obs_vision.get_current_scene()
                print(f"[xiaotang] OBS Vision: connected (scene: {scene})")
            else:
                print("[xiaotang] OBS Vision: offline (text-only)")
        
        # Auto-extract fresh bilibili cookies from persistent browser profile
        if self.bilibili_browser:
            print("[xiaotang] Extracting bilibili cookies from browser profile...")
            cookies = await asyncio.get_event_loop().run_in_executor(
                None, self.bilibili_browser.extract_cookies
            )
            if cookies.get("sessdata"):
                self.danmaku.update_credential(
                    sessdata=cookies["sessdata"],
                    bili_jct=cookies.get("bili_jct", ""),
                    buvid3=cookies.get("buvid3", ""),
                )
                print("[xiaotang] Fresh cookies loaded — danmaku will connect authenticated")
            else:
                print("[xiaotang] No cookies found — log into bilibili once in the bot's browser")

        # Register danmaku handler
        self.danmaku.on("danmaku", self._handle_danmaku)
        self.danmaku.on("viewer_enter", self._handle_viewer_enter)
        self.danmaku.on("live_start", self._on_live_start)
        self.danmaku.on("live_end", self._on_live_end)

        # Register voice listener handler and start if user is at computer
        if self.ears:
            self.ears.on("transcription", self._handle_voice_input)
            if self.afk_detector and not self.afk_detector.is_afk:
                await self.ears.start()
                print("[xiaotang] Voice listener: active (assistant mode)")
            elif not self.afk_detector:
                await self.ears.start()
                print("[xiaotang] Voice listener: active (always on)")

        # Start the response consumer loop
        asyncio.create_task(self._response_loop())

        # Start proactive commentary loop (assistant mode feature)
        if self.ears:
            asyncio.create_task(self._proactive_loop())

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
        if self.ears and self.ears.is_running:
            await self.ears.stop()
        if self.afk_detector:
            self.afk_detector.stop()
        if self.bilibili_browser:
            self.bilibili_browser.stop()
        if self.obs_vision:
            self.obs_vision.disconnect()
        await self.danmaku.stop()
        await self.overlay.stop()
        self.voice.cleanup()

    def _on_afk_start(self) -> None:
        """Called when user goes AFK - XiaoTang activates (streamer mode)."""
        print("[afk] User is AFK - XiaoTang is now active!")
        # Stop voice listener — switching to streamer mode
        if self.ears and self.ears.is_running and self._loop:
            asyncio.run_coroutine_threadsafe(self.ears.stop(), self._loop)
            print("[ears] Voice listener paused (streamer mode)")
        # Start Bilibili browser if enabled
        if self.bilibili_browser:
            try:
                self.bilibili_browser.start_browsing()
                print("[browser] Bilibili browsing task started")
            except Exception as e:
                print(f"[browser] Failed to start browser: {e}")

    def _on_afk_end(self) -> None:
        """Called when user returns - switch to assistant mode."""
        print("[afk] User returned - switching to assistant mode")
        # Flush any queued messages so the bot doesn't keep yapping
        self._flush_message_queue()
        # Stop Bilibili browser if running.
        # Run in a thread because this callback fires from pynput's listener
        # thread and stop() can block (join + driver.quit).
        if self.bilibili_browser:
            threading.Thread(
                target=self._stop_browser, daemon=True
            ).start()
        # Start voice listener — switching to assistant mode
        if self.ears and not self.ears.is_running and self._loop:
            asyncio.run_coroutine_threadsafe(self.ears.start(), self._loop)
            self._last_voice_input_at = time.time()
            print("[ears] Voice listener resumed (assistant mode)")

    def _flush_message_queue(self) -> None:
        """Drain and discard all queued messages."""
        dropped = 0
        while not self._message_queue.empty():
            try:
                self._message_queue.get_nowait()
                dropped += 1
            except asyncio.QueueEmpty:
                break
        if dropped:
            print(f"[afk] Flushed {dropped} queued message(s)")

    def _stop_browser(self) -> None:
        """Stop the browser (runs in its own thread to avoid blocking)."""
        try:
            self.bilibili_browser.stop()
            print("[browser] Bilibili browser stopped")
        except Exception as e:
            print(f"[browser] Failed to stop browser: {e}")

    def _is_active(self) -> bool:
        """Check if XiaoTang should be active (responding to messages)."""
        # If AFK mode is disabled, always active
        if not self.afk_detector:
            return True
        # If AFK mode enabled, only active when user is AFK
        return self.afk_detector.is_afk

    @staticmethod
    def _load_persona() -> str:
        """Load persona from the knowledge folder."""
        persona_path = Path(__file__).parent / "memory" / "knowledge" / "persona.txt"
        try:
            lines = persona_path.read_text(encoding="utf-8").splitlines()
            return "\n".join(
                l.strip() for l in lines if l.strip() and not l.strip().startswith("#")
            )
        except FileNotFoundError:
            return "Sharp-tongued, brutally honest, roasts everything."

    @staticmethod
    def _is_self_echo(transcription: str, current_tts: str) -> bool:
        """Check if a transcription is just the bot hearing its own TTS."""
        if not current_tts:
            return False
        t = transcription.lower().strip()
        c = current_tts.lower().strip()
        # If the transcription is a substring of what the bot is saying, it's echo
        if t in c or c in t:
            return True
        # Character overlap ratio
        t_chars = set(t)
        c_chars = set(c)
        if not t_chars:
            return False
        overlap = len(t_chars & c_chars) / len(t_chars)
        return overlap > 0.7

    async def _handle_voice_input(self, event: dict) -> None:
        """Handle transcribed voice input from the microphone."""
        text = event.get("text", "").strip()
        if not text:
            return

        # Filter common Whisper hallucinations on silence/noise
        HALLUCINATIONS = {
            "谢谢观看", "感谢观看", "thank you for watching",
            "请不吝点赞", "字幕由", "subtitles by",
            "thanks for watching", "thank you", "thank you.",
            "you", "bye", "bye.", "the end", "the end.",
            "嗯", "啊", "哦", "呃",
            "...", "。",
        }
        if text.lower().strip(" .。") in HALLUCINATIONS or len(text) < 2:
            print(f"[ears] Filtered hallucination: {text}")
            return

        # Self-echo check: if bot is speaking and text matches TTS output, ignore
        if self._is_speaking and self._is_self_echo(text, self._current_tts_text):
            print(f"[ears] Filtered self-echo: {text}")
            return

        # If bot is currently speaking, this is an interruption
        if self._is_speaking:
            print(f"[voice] Interruption: {text}")
            self._pending_interruption = text
            return

        # Normal voice input — enqueue like danmaku
        print(f"[voice] You said: {text}")
        self._recent_messages.append(f"(voice) douvle: {text}")
        self._last_voice_input_at = time.time()
        self._message_queue.put_nowait({
            "username": "douvle",
            "text": text,
            "source": "voice",
        })

    async def _handle_interruption(
        self, remaining_text: str, interruption_text: str
    ) -> str | None:
        """Ask the LLM how to handle an interruption.

        The LLM decides: yield and respond, or push back and keep talking.
        """
        language = detect_language(interruption_text)

        # Take a screenshot for context
        screenshot_b64 = None
        if self.obs_vision and self.obs_vision.is_connected:
            screenshot_b64 = self.obs_vision.take_screenshot()

        system_prompt = (
            f"{self._persona}\n\n"
            "You are XiaoTang (小糖). You were in the middle of speaking "
            "when the streamer interrupted you.\n"
            "You have TWO choices:\n"
            "1. YIELD: Stop what you were saying and respond to their interruption.\n"
            "2. PERSIST: Push back — tell them to let you finish, argue, or clap back.\n"
            "Choose naturally based on context. If they have a valid point, yield. "
            "If they're just being rude or impatient, persist and be sassy about it.\n"
            f"Reply in {language}. Keep it brief."
        )

        prompt = (
            f"You were saying: \"{remaining_text}\"\n"
            f"The streamer interrupted you: \"{interruption_text}\"\n"
            "How do you respond?"
        )

        messages = [{"role": "user", "content": prompt}]
        if screenshot_b64:
            messages = [{"role": "user", "content": [
                {"type": "image", "source": {
                    "type": "base64", "media_type": "image/png",
                    "data": screenshot_b64,
                }},
                {"type": "text", "text": prompt},
            ]}]

        try:
            return self.llm.generate(messages, system=system_prompt, max_tokens=200)
        except Exception as e:
            print(f"[llm_error] Interruption handling failed: {e}")
            return None

    async def _proactive_loop(self) -> None:
        """Proactively comment on stream when streamer is silent for too long."""
        timeout = self.settings.voice_proactive_timeout
        while True:
            await asyncio.sleep(30)  # Check every 30 seconds

            # Only when ears are active (assistant mode)
            if not self.ears or not self.ears.is_running:
                continue

            # Don't interrupt if bot is already speaking
            if self._is_speaking:
                continue

            # Check silence duration
            if self._last_voice_input_at <= 0:
                continue
            silence = time.time() - self._last_voice_input_at
            if silence < timeout:
                continue

            # Take a screenshot and comment
            screenshot_b64 = None
            if self.obs_vision and self.obs_vision.is_connected:
                screenshot_b64 = self.obs_vision.take_screenshot()
                if not screenshot_b64:
                    continue
            else:
                continue  # Need vision for proactive commentary

            print(f"[proactive] Streamer silent for {int(silence)}s — commenting")
            language = self.settings.default_language

            system_prompt = (
                f"{self._persona}\n\n"
                "You are XiaoTang (小糖). The streamer hasn't said anything for a while. "
                "Look at the screenshot and make a sassy comment about what they're doing. "
                "Be funny, roast them, or just make an observation. "
                f"Reply in {language}. Keep it to 1-2 sentences."
            )

            messages = [{"role": "user", "content": [
                {"type": "image", "source": {
                    "type": "base64", "media_type": "image/png",
                    "data": screenshot_b64,
                }},
                {"type": "text", "text": "What is the streamer doing right now? Comment on it."},
            ]}]

            try:
                reply = self.llm.generate(messages, system=system_prompt, max_tokens=100)
                if reply:
                    print(f"[proactive] {reply}")
                    self.memory.add_to_conversation("assistant", f"(proactive) {reply}")

                    segments = self._split_subtitles(reply)
                    self._is_speaking = True
                    if self.ears and self.ears.is_running:
                        self.ears.mute()
                    for i, segment in enumerate(segments):
                        self._current_tts_text = segment
                        try:
                            if i == 0:
                                await self.overlay.broadcast("小糖", "主动发言", segment)
                            else:
                                await self.overlay.update_subtitle(segment)
                        except Exception:
                            pass
                        try:
                            await self.voice.speak(segment, language)
                        except Exception:
                            pass
                    self._is_speaking = False
                    self._current_tts_text = ""
                    if self.ears and self.ears.is_running:
                        await asyncio.sleep(0.5)
                        self.ears.unmute()
                    try:
                        await self.overlay.hide()
                    except Exception:
                        pass
            except Exception as e:
                print(f"[proactive_error] {e}")

            # Reset timer so we don't spam
            self._last_voice_input_at = time.time()

    async def _handle_danmaku(self, msg: dict) -> None:
        """Handle incoming danmaku — just enqueue, no filtering."""
        text = msg.get("text", "")
        username = msg.get("username", "unknown")

        if not text:
            return

        print(f"[danmaku] {username}: {text}")
        self._recent_messages.append(f"{username}: {text}")

        # Check if XiaoTang is active (AFK mode check)
        if not self._is_active():
            return

        self._message_queue.put_nowait({"username": username, "text": text})

    async def _response_loop(self) -> None:
        """Consumer loop: drain queued messages, respond to them as a batch."""
        while True:
            # Wait for at least one message
            first = await self._message_queue.get()
            # Brief pause to let more messages stack up
            await asyncio.sleep(0.3)

            # Drain everything that accumulated
            batch = [first]
            while not self._message_queue.empty():
                try:
                    batch.append(self._message_queue.get_nowait())
                except asyncio.QueueEmpty:
                    break

            # Determine source (voice or danmaku)
            source = batch[0].get("source", "danmaku")
            is_voice = source == "voice"

            # For danmaku: check if XiaoTang is active (AFK mode)
            # Voice messages bypass this — they come from assistant mode
            if not is_voice and not self._is_active():
                print(f"[afk] Dropping {len(batch)} message(s) — user is back")
                continue

            # Aggregate into one prompt
            if len(batch) == 1:
                combined_text = f"{batch[0]['username']}: {batch[0]['text']}"
                display_user = batch[0]["username"]
                display_msg = batch[0]["text"] if not is_voice else "(voice)"
            else:
                lines = [f"{m['username']}: {m['text']}" for m in batch]
                combined_text = "\n".join(lines)
                display_user = ", ".join(dict.fromkeys(m["username"] for m in batch))
                display_msg = " / ".join(m["text"] for m in batch)
                if is_voice:
                    display_msg = "(voice)"
                print(f"[stack] Batched {len(batch)} messages")

            # Generate response
            reply = await self._generate_reply(combined_text, source=source)
            if not reply:
                continue

            print(f"[xiaotang] {reply}")

            # Record in memory
            for m in batch:
                self.memory.add_to_conversation("user", m["text"], m["username"])
            self.memory.add_to_conversation("assistant", reply)

            # Split reply into subtitle segments and play them one at a time
            language = detect_language(combined_text)
            segments = self._split_subtitles(reply)

            self._is_speaking = True
            self._pending_interruption = None
            # Mute mic during TTS to prevent echo
            if self.ears and self.ears.is_running:
                self.ears.mute()

            for i, segment in enumerate(segments):
                self._current_tts_text = segment

                try:
                    if i == 0:
                        await self.overlay.broadcast(display_user, display_msg, segment)
                    else:
                        await self.overlay.update_subtitle(segment)
                except Exception as e:
                    print(f"[overlay_error] {e}")

                try:
                    await self.voice.speak(segment, language)
                except Exception as e:
                    print(f"[tts_error] {e}")

                # Check for interruption between segments (set externally if
                # user spoke before mute kicked in)
                if self._pending_interruption and is_voice:
                    interruption = self._pending_interruption
                    self._pending_interruption = None
                    remaining = " ".join(segments[i + 1:])
                    print(f"[interrupt] Handling interruption: {interruption}")

                    int_reply = await self._handle_interruption(remaining, interruption)
                    if int_reply:
                        print(f"[xiaotang] (interrupt response) {int_reply}")
                        self.memory.add_to_conversation(
                            "user", f"(interrupted) {interruption}", "douvle"
                        )
                        self.memory.add_to_conversation("assistant", int_reply)

                        # Replace remaining segments with interruption response
                        int_segments = self._split_subtitles(int_reply)
                        int_lang = detect_language(interruption)
                        # Re-mute for interruption response TTS
                        if self.ears and self.ears.is_running:
                            self.ears.mute()
                        for j, iseg in enumerate(int_segments):
                            self._current_tts_text = iseg
                            try:
                                await self.overlay.update_subtitle(iseg)
                            except Exception:
                                pass
                            try:
                                await self.voice.speak(iseg, int_lang)
                            except Exception:
                                pass
                    break  # Stop original segments regardless

            self._is_speaking = False
            self._current_tts_text = ""
            # Unmute mic after TTS with delay for residual audio to fade
            if self.ears and self.ears.is_running:
                await asyncio.sleep(0.5)
                self.ears.unmute()

            try:
                await self.overlay.hide()
            except Exception as e:
                print(f"[overlay_error] {e}")

    @staticmethod
    def _split_subtitles(text: str, max_len: int = 30) -> list[str]:
        """Split a response into subtitle-sized segments for one-line display.

        Splits on sentence-ending punctuation first, then on commas/dashes
        if segments are still too long.  Returns at least one segment.
        """
        # Strip markdown bold/italic markers
        text = re.sub(r'\*{1,2}(.+?)\*{1,2}', r'\1', text)

        # Split on paragraph breaks first
        paragraphs = [p.strip() for p in text.split('\n') if p.strip()]

        segments: list[str] = []
        for para in paragraphs:
            if len(para) <= max_len:
                segments.append(para)
                continue

            # Split on sentence-ending punctuation (keep the punctuation attached)
            sentences = re.split(r'(?<=[。！？!?])\s*', para)

            for sentence in sentences:
                sentence = sentence.strip()
                if not sentence:
                    continue
                if len(sentence) <= max_len:
                    segments.append(sentence)
                    continue

                # Still too long — split on comma-like punctuation
                parts = re.split(r'(?<=[，,、；;])\s*|(?<=——)', sentence)
                current = ""
                for part in parts:
                    part = part.strip()
                    if not part:
                        continue
                    if current and len(current) + len(part) > max_len:
                        segments.append(current)
                        current = part
                    else:
                        current += part
                if current:
                    segments.append(current)

        return segments if segments else [text]

    async def _generate_reply(
        self, user_message: str, source: str = "danmaku"
    ) -> str | None:
        """Generate a reply using the LLM, optionally with a screenshot."""
        language = detect_language(user_message)

        # Get relevant memories
        memory_hits = select_memory(self._memory_lines, user_message)
        recent_highlights = list(self._recent_messages)[-self.settings.max_context_messages:]

        persona = self._persona

        # Try to capture a screenshot from OBS for visual context
        screenshot_b64 = None
        if self.obs_vision and self.obs_vision.is_connected:
            screenshot_b64 = self.obs_vision.take_screenshot()
            if screenshot_b64:
                print("[obs] Screenshot captured for visual context")

        system_prompt, messages = build_messages(
            persona=persona,
            language=language,
            memory_lines=memory_hits,
            recent_messages=recent_highlights,
            user_message=user_message,
            screenshot_base64=screenshot_b64,
        )

        try:
            return self.llm.generate(messages, system=system_prompt)
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

        system_prompt = (
            "You are XiaoTang (小糖), a sassy and playful AI streaming companion. "
            "When a new viewer enters, welcome them by NAME and make a witty, playful roast about their username. "
            "Be cheeky but not mean - the goal is to make them laugh and engage. "
            "Examples of good roasts: '哎呀 [爱吃键盘的大唐] 来了！键盘好吃吗？薄膜的还是机械的？' "
            "or '欢迎 [某某某]！这名字起的...你爸妈知道吗？哈哈开玩笑的~' "
            "Keep it under 25 words. Must include their actual username. "
            f"Reply in {language}."
        )

        messages = [
            {"role": "user", "content": f"New viewer just entered: {username}"},
        ]

        try:
            welcome_msg = self.llm.generate(messages, system=system_prompt, max_tokens=50)
            print(f"[xiaotang] (welcome) {welcome_msg}")

            # Show on overlay, speak, then hide
            await self.overlay.broadcast(username, "进入直播间", welcome_msg)
            await self.voice.speak(welcome_msg, language)
            await self.overlay.hide()
        except Exception as e:
            print(f"[welcome_error] {e}")


async def main() -> None:
    """Main entry point."""
    xiaotang = XiaoTang()
    await xiaotang.start()


if __name__ == "__main__":
    asyncio.run(main())
