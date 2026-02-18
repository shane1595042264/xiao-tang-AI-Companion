from __future__ import annotations

import asyncio
import os
import tempfile

import edge_tts
import pygame


# Voice options - pick based on language
VOICE_CHINESE = "zh-CN-XiaoxiaoNeural"  # Female, cute
VOICE_ENGLISH = "en-US-AnaNeural"  # Female, friendly

# Alternative voices:
# Chinese: zh-CN-XiaoyiNeural, zh-CN-YunxiNeural (male)
# English: en-US-AriaNeural, en-US-JennyNeural


class TTSEngine:
    def __init__(self) -> None:
        pygame.mixer.init()
        self._lock = asyncio.Lock()
        self._temp_dir = tempfile.mkdtemp(prefix="xiaotang_tts_")

    async def speak(self, text: str, language: str = "Chinese") -> None:
        """Generate TTS audio and play it."""
        voice = VOICE_CHINESE if language == "Chinese" else VOICE_ENGLISH

        async with self._lock:
            # Generate audio file
            temp_file = os.path.join(self._temp_dir, "speech.mp3")

            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(temp_file)

            # Play audio
            try:
                pygame.mixer.music.load(temp_file)
                pygame.mixer.music.play()

                # Wait for playback to finish
                while pygame.mixer.music.get_busy():
                    await asyncio.sleep(0.1)
            except Exception as e:
                print(f"[tts_error] Playback failed: {e}")
            finally:
                # Clean up
                pygame.mixer.music.unload()
                try:
                    os.remove(temp_file)
                except OSError:
                    pass

    def cleanup(self) -> None:
        """Clean up resources."""
        pygame.mixer.quit()
        try:
            os.rmdir(self._temp_dir)
        except OSError:
            pass
