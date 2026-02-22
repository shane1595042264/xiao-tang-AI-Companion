from __future__ import annotations

from dataclasses import dataclass
import os

from dotenv import load_dotenv


@dataclass
class Settings:
    room_id: int
    sessdata: str | None
    buvid3: str | None
    bili_jct: str | None
    anthropic_api_key: str
    anthropic_model: str
    response_cooldown_sec: float
    max_context_messages: int
    memory_path: str
    default_language: str
    welcome_new_viewers: bool
    afk_mode: bool
    afk_timeout_minutes: float
    afk_browse_bilibili: bool
    afk_browse_category: str
    afk_video_duration_min: int
    afk_video_duration_max: int
    # OBS Vision
    obs_vision_enabled: bool
    obs_host: str
    obs_port: int
    obs_password: str
    obs_screenshot_width: int
    obs_screenshot_height: int
    # Voice Listener (Ears)
    voice_listen_enabled: bool
    groq_api_key: str
    voice_device_index: int | None
    voice_vad_aggressiveness: int
    voice_proactive_timeout: int


def load_settings() -> Settings:
    load_dotenv()
    room_id_raw = os.getenv("BILIBILI_ROOM_ID", "").strip()
    if not room_id_raw.isdigit():
        raise ValueError("BILIBILI_ROOM_ID must be set to a numeric room id")

    sessdata = os.getenv("BILIBILI_SESSDATA", "").strip() or None
    buvid3 = os.getenv("BILIBILI_BUVID3", "").strip() or None
    bili_jct = os.getenv("BILIBILI_BILI_JCT", "").strip() or None

    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY must be set")

    model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")

    cooldown = float(os.getenv("RESPONSE_COOLDOWN_SEC", "10"))
    max_context = int(os.getenv("MAX_CONTEXT_MESSAGES", "6"))

    default_memory_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "memory.txt")
    )
    memory_path = os.getenv("MEMORY_PATH", default_memory_path)

    default_language = os.getenv("DEFAULT_LANGUAGE", "Chinese")
    welcome_new_viewers = os.getenv("WELCOME_NEW_VIEWERS", "true").lower() in ("true", "1", "yes")

    afk_mode = os.getenv("AFK_MODE", "false").lower() in ("true", "1", "yes")
    afk_timeout_minutes = float(os.getenv("AFK_TIMEOUT_MINUTES", "1"))

    # AFK Bilibili browsing settings
    afk_browse_bilibili = os.getenv("AFK_BROWSE_BILIBILI", "false").lower() in ("true", "1", "yes")
    afk_browse_category = os.getenv("AFK_BROWSE_CATEGORY", "hot")
    afk_video_duration_min = int(os.getenv("AFK_VIDEO_DURATION_MIN", "60"))
    afk_video_duration_max = int(os.getenv("AFK_VIDEO_DURATION_MAX", "600"))

    # OBS Vision settings
    obs_vision_enabled = os.getenv("OBS_VISION_ENABLED", "false").lower() in ("true", "1", "yes")
    obs_host = os.getenv("OBS_HOST", "localhost")
    obs_port = int(os.getenv("OBS_PORT", "4455"))
    obs_password = os.getenv("OBS_PASSWORD", "")
    obs_screenshot_width = int(os.getenv("OBS_SCREENSHOT_WIDTH", "1280"))
    obs_screenshot_height = int(os.getenv("OBS_SCREENSHOT_HEIGHT", "720"))

    # Voice Listener settings
    voice_listen_enabled = os.getenv("VOICE_LISTEN_ENABLED", "false").lower() in ("true", "1", "yes")
    groq_api_key = os.getenv("GROQ_API_KEY", "").strip()
    voice_device_raw = os.getenv("VOICE_DEVICE_INDEX", "").strip()
    voice_device_index = int(voice_device_raw) if voice_device_raw.isdigit() else None
    voice_vad_aggressiveness = int(os.getenv("VOICE_VAD_AGGRESSIVENESS", "2"))
    voice_proactive_timeout = int(os.getenv("VOICE_PROACTIVE_TIMEOUT", "300"))

    return Settings(
        room_id=int(room_id_raw),
        sessdata=sessdata,
        buvid3=buvid3,
        bili_jct=bili_jct,
        anthropic_api_key=api_key,
        anthropic_model=model,
        response_cooldown_sec=cooldown,
        max_context_messages=max_context,
        memory_path=memory_path,
        default_language=default_language,
        welcome_new_viewers=welcome_new_viewers,
        afk_mode=afk_mode,
        afk_timeout_minutes=afk_timeout_minutes,
        afk_browse_bilibili=afk_browse_bilibili,
        afk_browse_category=afk_browse_category,
        afk_video_duration_min=afk_video_duration_min,
        afk_video_duration_max=afk_video_duration_max,
        obs_vision_enabled=obs_vision_enabled,
        obs_host=obs_host,
        obs_port=obs_port,
        obs_password=obs_password,
        obs_screenshot_width=obs_screenshot_width,
        obs_screenshot_height=obs_screenshot_height,
        voice_listen_enabled=voice_listen_enabled,
        groq_api_key=groq_api_key,
        voice_device_index=voice_device_index,
        voice_vad_aggressiveness=voice_vad_aggressiveness,
        voice_proactive_timeout=voice_proactive_timeout,
    )
