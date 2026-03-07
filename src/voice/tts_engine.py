"""TTS Engine - Text-to-speech synthesis using Microsoft Edge TTS."""

from __future__ import annotations

import asyncio
import os
import tempfile
import threading

import edge_tts
import pygame

try:
    import numpy as np
    import sounddevice as sd
    SOUNDDEVICE_AVAILABLE = True
except ImportError:
    SOUNDDEVICE_AVAILABLE = False


# Voice options by language
VOICES = {
    "Chinese": {
        "default": "zh-CN-XiaoxiaoNeural",  # Female, cute
        "alternatives": [
            "zh-CN-XiaoyiNeural",   # Female, gentle
            "zh-CN-YunxiNeural",    # Male, young
            "zh-CN-YunjianNeural",  # Male, narrator
        ],
    },
    "English": {
        "default": "en-US-AriaNeural",  # Female, expressive (matches Xiaoxiao's tone)
        "alternatives": [
            "en-US-JennyNeural",   # Female, conversational
            "en-US-AnaNeural",     # Female, child-like
            "en-US-GuyNeural",     # Male, casual
        ],
    },
    "Japanese": {
        "default": "ja-JP-NanamiNeural",
        "alternatives": ["ja-JP-KeitaNeural"],
    },
}


def _find_virtual_cable_device() -> int | None:
    """Find the VB-Audio Virtual Cable input device index."""
    if not SOUNDDEVICE_AVAILABLE:
        return None
    try:
        devices = sd.query_devices()
        for i, d in enumerate(devices):
            name = d.get("name", "").lower()
            if "cable input" in name and "vb-audio" in name and d["max_output_channels"] > 0:
                return i
    except Exception:
        pass
    return None


class TTSEngine:
    """Text-to-speech engine using Microsoft Edge TTS."""

    def __init__(self, default_voice: str | None = None) -> None:
        pygame.mixer.init()
        self._lock = asyncio.Lock()
        self._temp_dir = tempfile.mkdtemp(prefix="xiaotang_tts_")
        self._default_voice = default_voice

        # Find virtual cable for VTuber lip sync
        self._virtual_cable_device = _find_virtual_cable_device()
        if self._virtual_cable_device is not None:
            print(f"[tts] Virtual cable found (device {self._virtual_cable_device}) — lip sync enabled")
        else:
            print("[tts] No virtual cable found — lip sync disabled")

    def get_voice(self, language: str) -> str:
        """Get the voice for a given language."""
        if self._default_voice:
            return self._default_voice
        return VOICES.get(language, VOICES["English"])["default"]

    async def speak(self, text: str, language: str = "Chinese") -> None:
        """Generate TTS audio and play it on headphones + virtual cable."""
        voice = self.get_voice(language)

        async with self._lock:
            temp_file = os.path.join(self._temp_dir, "speech.mp3")

            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(temp_file)

            try:
                # Play on headphones via pygame
                pygame.mixer.music.load(temp_file)
                pygame.mixer.music.play()

                # Simultaneously play on virtual cable for VTuber lip sync
                if self._virtual_cable_device is not None and SOUNDDEVICE_AVAILABLE:
                    self._play_on_virtual_cable(temp_file)

                # Wait for playback to finish
                while pygame.mixer.music.get_busy():
                    await asyncio.sleep(0.1)
            except Exception as e:
                print(f"[tts_error] Playback failed: {e}")
            finally:
                pygame.mixer.music.unload()
                try:
                    os.remove(temp_file)
                except OSError:
                    pass

    def _play_on_virtual_cable(self, mp3_path: str) -> None:
        """Play audio on the virtual cable device using pygame Sound + sounddevice."""
        try:
            # Load MP3 via pygame and extract raw PCM
            sound = pygame.mixer.Sound(mp3_path)
            raw = sound.get_raw()

            # Convert to numpy float32 array
            # pygame mixer default: 16-bit signed, system sample rate
            mixer_info = pygame.mixer.get_init()
            if not mixer_info:
                return
            sample_rate, bits, channels = mixer_info

            samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            if channels == 2:
                samples = samples.reshape((-1, 2))
            elif channels == 1:
                samples = samples.reshape((-1, 1))

            # Play non-blocking on virtual cable in background thread
            def _play():
                try:
                    sd.play(samples, samplerate=sample_rate, device=self._virtual_cable_device)
                    sd.wait()
                except Exception:
                    pass

            threading.Thread(target=_play, daemon=True).start()
        except Exception as e:
            print(f"[tts] Virtual cable playback failed: {e}")

    async def speak_async(self, text: str, language: str = "Chinese") -> None:
        """Non-blocking speech - fire and forget."""
        asyncio.create_task(self.speak(text, language))

    def set_voice(self, voice: str) -> None:
        """Set a custom voice."""
        self._default_voice = voice

    def cleanup(self) -> None:
        """Clean up resources."""
        pygame.mixer.quit()
        try:
            os.rmdir(self._temp_dir)
        except OSError:
            pass

    @staticmethod
    def list_voices() -> dict:
        """Return available voice options."""
        return VOICES
