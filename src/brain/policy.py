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
    """Check if a message passes content safety filters."""
    lowered = message.lower()
    for term in _BAD_TERMS:
        if term in lowered:
            return False
    return True


def is_low_value_message(message: str) -> bool:
    """Check if a message is too low-value to respond to."""
    stripped = message.strip()
    
    # Allow "?" and "？" as valid question markers
    if stripped in ("?", "？", "!", "！"):
        return False
    
    if len(stripped) < 2:
        return True

    # Repeated single character spam
    if len(set(message)) == 1 and len(message) > 3:
        return True

    # All caps ASCII without CJK (usually spam)
    if _CJK_RE.search(message) is None and message.isascii() and message.isupper():
        return True

    return False


def detect_language(message: str) -> str:
    """Detect if message is primarily Chinese or English."""
    if _CJK_RE.search(message):
        return "Chinese"
    return "English"
