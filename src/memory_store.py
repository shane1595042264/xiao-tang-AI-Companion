from __future__ import annotations

import re
from typing import Iterable


_WORD_RE = re.compile(r"[a-zA-Z]{4,}")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def load_memory_lines(path: str) -> list[str]:
    with open(path, "r", encoding="utf-8") as file:
        lines = [line.strip() for line in file.readlines()]
    return [line for line in lines if line]


def _extract_keywords(message: str) -> tuple[list[str], list[str]]:
    english = [match.group(0).lower() for match in _WORD_RE.finditer(message)]
    cjk = _CJK_RE.findall(message)
    return english, cjk


def _score_line(line: str, english: Iterable[str], cjk: Iterable[str]) -> int:
    score = 0
    lower_line = line.lower()
    for word in english:
        if word in lower_line:
            score += 2
    for char in cjk:
        if char in line:
            score += 1
    return score


def select_memory(lines: list[str], message: str, max_lines: int = 4) -> list[str]:
    english, cjk = _extract_keywords(message)
    if not english and not cjk:
        return []

    scored = []
    for line in lines:
        score = _score_line(line, english, cjk)
        if score > 0:
            scored.append((score, line))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [line for _, line in scored[:max_lines]]
