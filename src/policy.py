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
    "\u81ea\u6740",
    "\u81ea\u4f24",
    "\u8272\u60c5",
]


def is_message_allowed(message: str) -> bool:
    lowered = message.lower()
    for term in _BAD_TERMS:
        if term in lowered:
            return False
    return True


def is_low_value_message(message: str) -> bool:
    if len(message.strip()) < 2:
        return True

    if len(set(message)) == 1 and len(message) > 3:
        return True

    if _CJK_RE.search(message) is None and message.isascii() and message.isupper():
        return True

    return False
