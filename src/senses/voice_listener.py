"""Voice Listener - Microphone input with VAD and Groq Whisper transcription."""

from __future__ import annotations

import asyncio
import io
import threading
import time
import wave
from collections import deque
from typing import Any, Callable, Optional

try:
    import sounddevice as sd
    SOUNDDEVICE_AVAILABLE = True
except (ImportError, OSError):
    SOUNDDEVICE_AVAILABLE = False

try:
    import webrtcvad
    WEBRTCVAD_AVAILABLE = True
except ImportError:
    WEBRTCVAD_AVAILABLE = False

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

try:
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioMeterInformation
    PYCAW_AVAILABLE = True
except ImportError:
    PYCAW_AVAILABLE = False

VOICE_LISTEN_AVAILABLE = (
    SOUNDDEVICE_AVAILABLE and WEBRTCVAD_AVAILABLE
    and NUMPY_AVAILABLE and HTTPX_AVAILABLE
)


def is_voice_listen_available() -> bool:
    """Check if all voice listening dependencies are installed."""
    return VOICE_LISTEN_AVAILABLE


class VoiceListener:
    """
    Listens to microphone input, detects speech via VAD,
    and transcribes using Groq Whisper API.

    This is XiaoTang's "ears" for the streamer's voice.
    Follows the same event-driven pattern as DanmakuListener.
    """

    # Audio constants
    SAMPLE_RATE = 16000          # 16kHz mono — optimal for Whisper
    CHANNELS = 1
    DTYPE = "int16"
    FRAME_DURATION_MS = 30       # webrtcvad requires 10/20/30ms frames
    FRAME_SIZE = SAMPLE_RATE * FRAME_DURATION_MS // 1000  # 480 samples

    # VAD tuning
    SPEECH_START_FRAMES = 8      # Consecutive voiced frames to start recording
    SILENCE_END_FRAMES = 30      # Consecutive silent frames to stop (30 * 30ms = 900ms)
    MIN_SPEECH_DURATION_S = 0.8  # Discard segments shorter than this
    MAX_SPEECH_DURATION_S = 30.0 # Force-end segments longer than this
    ENERGY_THRESHOLD = 300       # RMS energy threshold — below this is background noise
    SYSTEM_AUDIO_PEAK = 0.01     # System audio peak above this = something is playing

    # Groq API
    GROQ_TRANSCRIPTION_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
    WHISPER_MODEL = "whisper-large-v3"

    def __init__(
        self,
        groq_api_key: str,
        device_index: int | None = None,
        vad_aggressiveness: int = 3,
    ) -> None:
        if not VOICE_LISTEN_AVAILABLE:
            missing = []
            if not SOUNDDEVICE_AVAILABLE:
                missing.append("sounddevice")
            if not WEBRTCVAD_AVAILABLE:
                missing.append("webrtcvad-wheels")
            if not NUMPY_AVAILABLE:
                missing.append("numpy")
            if not HTTPX_AVAILABLE:
                missing.append("httpx")
            raise ImportError(
                f"Voice listening requires: {', '.join(missing)}. "
                f"Install with: pip install {' '.join(missing)}"
            )

        self._groq_api_key = groq_api_key
        self._device_index = device_index
        self._vad = webrtcvad.Vad(vad_aggressiveness)

        self._handlers: dict[str, list[Callable]] = {}
        self._running = False
        self._muted = False
        self._capture_thread: threading.Thread | None = None

        # System audio peak meter (Windows only via pycaw)
        self._audio_meter = None
        if PYCAW_AVAILABLE:
            try:
                speakers = AudioUtilities.GetSpeakers()
                meter_iface = speakers.Activate(
                    IAudioMeterInformation._iid_, CLSCTX_ALL, None
                )
                self._audio_meter = meter_iface.QueryInterface(
                    IAudioMeterInformation
                )
            except Exception:
                pass  # Non-critical — bot works without it
        self._loop: asyncio.AbstractEventLoop | None = None
        self._http_client: httpx.AsyncClient | None = None

    # -- Event system (mirrors DanmakuListener) --

    def on(self, event_type: str, handler: Callable) -> None:
        """Register an event handler.

        Events:
            "transcription": {"text": str, "duration": float, "timestamp": float}
            "speech_start": {}
            "speech_end": {"duration": float}
            "error": {"error": str}
        """
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
                print(f"[ears_error] Handler error: {e}")

    def _dispatch_threadsafe(self, event_type: str, event: dict) -> None:
        """Dispatch from the capture thread into the asyncio event loop."""
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self._dispatch(event_type, event), self._loop
            )

    # -- Lifecycle --

    async def start(self) -> None:
        """Start listening to the microphone."""
        if self._running:
            return

        self._loop = asyncio.get_running_loop()
        self._http_client = httpx.AsyncClient(timeout=30.0)
        self._running = True

        self._capture_thread = threading.Thread(
            target=self._capture_loop, daemon=True, name="voice-capture"
        )
        self._capture_thread.start()
        print("[ears] Voice listener started (microphone active)")

    async def stop(self) -> None:
        """Stop listening."""
        self._running = False
        if self._capture_thread and self._capture_thread.is_alive():
            self._capture_thread.join(timeout=3.0)
        self._capture_thread = None
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
        print("[ears] Voice listener stopped")

    def mute(self) -> None:
        """Mute the mic (during TTS to prevent echo)."""
        self._muted = True

    def unmute(self) -> None:
        """Unmute the mic after TTS."""
        self._muted = False

    def is_system_audio_playing(self) -> bool:
        """Check if system audio output is active (video, music, etc.)."""
        if not self._audio_meter:
            return False
        try:
            peak = self._audio_meter.GetPeakValue()
            return peak > self.SYSTEM_AUDIO_PEAK
        except Exception:
            return False

    @property
    def is_running(self) -> bool:
        return self._running

    # -- Audio capture thread --

    def _capture_loop(self) -> None:
        """Background thread: capture audio, detect speech, send for transcription."""
        try:
            stream = sd.InputStream(
                samplerate=self.SAMPLE_RATE,
                channels=self.CHANNELS,
                dtype=self.DTYPE,
                blocksize=self.FRAME_SIZE,
                device=self._device_index,
            )
            stream.start()
        except Exception as e:
            self._dispatch_threadsafe("error", {"error": f"Mic open failed: {e}"})
            print(f"[ears_error] Cannot open microphone: {e}")
            return

        # VAD state machine
        ring_buffer: deque[tuple[bytes, bool]] = deque(
            maxlen=self.SPEECH_START_FRAMES
        )
        speech_frames: list[bytes] = []
        is_speaking = False
        speech_start_time = 0.0
        silent_frame_count = 0

        try:
            while self._running:
                try:
                    data, overflowed = stream.read(self.FRAME_SIZE)
                except Exception:
                    continue

                raw_bytes = data.tobytes()

                # If muted (TTS playing), discard audio and reset state
                if self._muted:
                    if is_speaking:
                        is_speaking = False
                        speech_frames.clear()
                        ring_buffer.clear()
                        silent_frame_count = 0
                    continue

                # Energy check — skip frames that are just background noise
                frame_array = np.frombuffer(raw_bytes, dtype=np.int16)
                rms = np.sqrt(np.mean(frame_array.astype(np.float32) ** 2))

                # VAD analysis
                try:
                    is_voiced = self._vad.is_speech(raw_bytes, self.SAMPLE_RATE)
                except Exception:
                    continue
                # Override VAD if energy is too low — it's noise, not speech
                if rms < self.ENERGY_THRESHOLD:
                    is_voiced = False

                if not is_speaking:
                    # Accumulate in ring buffer, looking for speech onset
                    ring_buffer.append((raw_bytes, is_voiced))
                    voiced_count = sum(1 for _, v in ring_buffer if v)

                    if voiced_count >= self.SPEECH_START_FRAMES:
                        # Speech detected!
                        is_speaking = True
                        speech_start_time = time.time()
                        silent_frame_count = 0
                        speech_frames = [f for f, _ in ring_buffer]
                        ring_buffer.clear()
                        self._dispatch_threadsafe("speech_start", {})
                else:
                    # Currently recording speech
                    speech_frames.append(raw_bytes)

                    if not is_voiced:
                        silent_frame_count += 1
                    else:
                        silent_frame_count = 0

                    duration = time.time() - speech_start_time

                    # End conditions: enough silence or max duration
                    if (
                        silent_frame_count >= self.SILENCE_END_FRAMES
                        or duration >= self.MAX_SPEECH_DURATION_S
                    ):
                        is_speaking = False
                        self._dispatch_threadsafe(
                            "speech_end", {"duration": duration}
                        )

                        # Only transcribe if long enough and loud enough
                        avg_energy = 0.0
                        if speech_frames:
                            all_audio = np.frombuffer(
                                b"".join(speech_frames), dtype=np.int16
                            )
                            avg_energy = np.sqrt(
                                np.mean(all_audio.astype(np.float32) ** 2)
                            )

                        if duration < self.MIN_SPEECH_DURATION_S:
                            print(
                                f"[ears] Discarded short segment "
                                f"({duration:.1f}s < {self.MIN_SPEECH_DURATION_S}s)"
                            )
                        elif avg_energy < self.ENERGY_THRESHOLD:
                            print(
                                f"[ears] Discarded quiet segment "
                                f"(energy {avg_energy:.0f} < {self.ENERGY_THRESHOLD})"
                            )
                        elif self.is_system_audio_playing():
                            print("[ears] System audio active — ignoring mic input")
                        else:
                            wav_bytes = self._frames_to_wav(speech_frames)
                            if self._loop and self._loop.is_running():
                                asyncio.run_coroutine_threadsafe(
                                    self._transcribe_and_dispatch(
                                        wav_bytes, duration
                                    ),
                                    self._loop,
                                )

                        speech_frames.clear()
                        ring_buffer.clear()
                        silent_frame_count = 0

        except Exception as e:
            print(f"[ears_error] Capture loop error: {e}")
            self._dispatch_threadsafe("error", {"error": str(e)})
        finally:
            stream.stop()
            stream.close()

    def _frames_to_wav(self, frames: list[bytes]) -> bytes:
        """Convert raw PCM frames into a WAV file in memory."""
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(self.CHANNELS)
            wf.setsampwidth(2)  # 16-bit = 2 bytes
            wf.setframerate(self.SAMPLE_RATE)
            wf.writeframes(b"".join(frames))
        return buf.getvalue()

    # -- Groq Whisper transcription --

    async def _transcribe_and_dispatch(
        self, wav_bytes: bytes, duration: float
    ) -> None:
        """Send audio to Groq Whisper and dispatch the transcription event."""
        try:
            text = await self._transcribe(wav_bytes)
            if text and text.strip():
                print(f"[ears] Heard: {text}")
                await self._dispatch("transcription", {
                    "text": text.strip(),
                    "duration": duration,
                    "timestamp": time.time(),
                })
            else:
                print("[ears] (empty transcription, ignoring)")
        except Exception as e:
            print(f"[ears_error] Transcription failed: {e}")
            await self._dispatch("error", {"error": f"Transcription: {e}"})

    async def _transcribe(self, wav_bytes: bytes) -> str:
        """Call Groq Whisper API to transcribe audio."""
        if not self._http_client:
            return ""

        response = await self._http_client.post(
            self.GROQ_TRANSCRIPTION_URL,
            headers={"Authorization": f"Bearer {self._groq_api_key}"},
            files={"file": ("speech.wav", wav_bytes, "audio/wav")},
            data={
                "model": self.WHISPER_MODEL,
                "response_format": "json",
            },
        )
        response.raise_for_status()
        result = response.json()
        return result.get("text", "")
