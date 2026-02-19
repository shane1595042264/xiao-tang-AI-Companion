"""TTS Engine - Text-to-speech synthesis using Microsoft Edge TTS."""

from __future__ import annotations

import asyncio
import os
import tempfile

import edge_tts
import pygame


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
        "default": "en-US-AnaNeural",  # Female, friendly
        "alternatives": [
            "en-US-AriaNeural",    # Female, expressive
            "en-US-JennyNeural",   # Female, conversational
            "en-US-GuyNeural",     # Male, casual
        ],
    },
    "Japanese": {
        "default": "ja-JP-NanamiNeural",
        "alternatives": ["ja-JP-KeitaNeural"],
    },
}


class TTSEngine:
    """Text-to-speech engine using Microsoft Edge TTS."""

    def __init__(self, default_voice: str | None = None) -> None:
        pygame.mixer.init()
        self._lock = asyncio.Lock()
        self._temp_dir = tempfile.mkdtemp(prefix="xiaotang_tts_")
        self._default_voice = default_voice

    def get_voice(self, language: str) -> str:
        """Get the voice for a given language."""
        if self._default_voice:
            return self._default_voice
        return VOICES.get(language, VOICES["English"])["default"]

    async def speak(self, text: str, language: str = "Chinese") -> None:
        """Generate TTS audio and play it."""
        voice = self.get_voice(language)

        async with self._lock:
            temp_file = os.path.join(self._temp_dir, "speech.mp3")

            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(temp_file)

            try:
                pygame.mixer.music.load(temp_file)
                pygame.mixer.music.play()

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
