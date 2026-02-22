"""Policy - Content filtering and message safety checks."""

from __future__ import annotations

import re


_CJK_RE = re.compile(r"[\u4e00-\u9fff]")

_BAD_TERMS = [
    "suicide",
    "self-harm",
    "kill myself",
    "porn",
    "sex",
    "nude",
    "doxx",
    "terror",
    "bomb",
    "weapon",
    "drugs",
    "illegal",
    "exploit",
    "malware",
    "ransom",
    "\u81ea\u6740",  # 自杀
    "\u81ea\u4f24",  # 自伤
    "\u8272\u60c5",  # 色情
]


def is_message_allowed(message: str) -> bool:
    """No filtering — bot is unfiltered."""
    return True


def is_low_value_message(message: str) -> bool:
    """No filtering — respond to everything."""
    return False


def detect_language(message: str) -> str:
    """Detect if message is primarily Chinese or English."""
    if _CJK_RE.search(message):
        return "Chinese"
    return "English"
