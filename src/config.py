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
    openai_api_key: str
    openai_model: str
    openai_base_url: str | None
    response_cooldown_sec: float
    max_context_messages: int
    memory_path: str


def load_settings() -> Settings:
    load_dotenv()
    room_id_raw = os.getenv("BILIBILI_ROOM_ID", "").strip()
    if not room_id_raw.isdigit():
        raise ValueError("BILIBILI_ROOM_ID must be set to a numeric room id")

    sessdata = os.getenv("BILIBILI_SESSDATA", "").strip() or None
    buvid3 = os.getenv("BILIBILI_BUVID3", "").strip() or None
    bili_jct = os.getenv("BILIBILI_BILI_JCT", "").strip() or None

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("OPENAI_API_KEY must be set")

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    base_url = os.getenv("OPENAI_BASE_URL")

    cooldown = float(os.getenv("RESPONSE_COOLDOWN_SEC", "10"))
    max_context = int(os.getenv("MAX_CONTEXT_MESSAGES", "6"))

    default_memory_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "memory.txt")
    )
    memory_path = os.getenv("MEMORY_PATH", default_memory_path)

    return Settings(
        room_id=int(room_id_raw),
        sessdata=sessdata,
        buvid3=buvid3,
        bili_jct=bili_jct,
        openai_api_key=api_key,
        openai_model=model,
        openai_base_url=base_url,
        response_cooldown_sec=cooldown,
        max_context_messages=max_context,
        memory_path=memory_path,
    )
