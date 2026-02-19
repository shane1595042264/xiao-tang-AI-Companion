"""
Memory Store - Semantic storage and retrieval for XiaoTang's memories.

Uses keyword-based matching with optional embedding support for future.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Optional


_WORD_RE = re.compile(r"[a-zA-Z]{3,}")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


class MemoryEntry:
    """A single memory entry with text and metadata."""

    def __init__(
        self,
        text: str,
        category: str = "general",
        metadata: Optional[dict] = None,
    ) -> None:
        self.text = text
        self.category = category
        self.metadata = metadata or {}
        self.metadata["category"] = category
        
        # Pre-compute keywords for fast matching
        self._keywords_en = set(w.lower() for w in _WORD_RE.findall(text))
        self._keywords_cjk = set(_CJK_RE.findall(text))

    def score(self, query_en: set[str], query_cjk: set[str]) -> float:
        """Calculate relevance score against query keywords."""
        if not self._keywords_en and not self._keywords_cjk:
            return 0.0
        
        en_matches = len(self._keywords_en & query_en)
        cjk_matches = len(self._keywords_cjk & query_cjk)
        
        # Normalize by query size
        total_query = len(query_en) + len(query_cjk)
        if total_query == 0:
            return 0.0
        
        return (en_matches * 2 + cjk_matches) / (total_query * 2)


class MemoryStore:
    """
    Semantic memory storage with keyword-based retrieval.
    
    Future: Can add vector embeddings for better semantic search.
    """

    def __init__(self) -> None:
        self._memories: list[MemoryEntry] = []
        self._index: dict[str, list[int]] = {}  # keyword -> memory indices

    def add(
        self,
        text: str,
        category: str = "general",
        metadata: Optional[dict] = None,
    ) -> None:
        """Add a memory to the store."""
        # Avoid duplicates
        for mem in self._memories:
            if mem.text == text:
                return
        
        entry = MemoryEntry(text, category, metadata)
        idx = len(self._memories)
        self._memories.append(entry)
        
        # Index by keywords
        for kw in entry._keywords_en:
            self._index.setdefault(kw, []).append(idx)
        for kw in entry._keywords_cjk:
            self._index.setdefault(kw, []).append(idx)

    def search(
        self,
        query: str,
        max_results: int = 5,
        category: Optional[str] = None,
    ) -> list[tuple[str, float, dict]]:
        """
        Search for relevant memories.
        
        Returns:
            List of (text, score, metadata) tuples
        """
        query_en = set(w.lower() for w in _WORD_RE.findall(query))
        query_cjk = set(_CJK_RE.findall(query))
        
        if not query_en and not query_cjk:
            return []
        
        # Find candidate memories via index
        candidates = set()
        for kw in query_en:
            candidates.update(self._index.get(kw, []))
        for kw in query_cjk:
            candidates.update(self._index.get(kw, []))
        
        # Score candidates
        scored = []
        for idx in candidates:
            mem = self._memories[idx]
            if category and mem.category != category:
                continue
            score = mem.score(query_en, query_cjk)
            if score > 0:
                scored.append((mem.text, score, mem.metadata))
        
        # Sort by score and return top results
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:max_results]

    def remove(self, text: str) -> bool:
        """Remove a memory by exact text match."""
        for i, mem in enumerate(self._memories):
            if mem.text == text:
                self._memories.pop(i)
                # Rebuild index (simple approach)
                self._rebuild_index()
                return True
        return False

    def _rebuild_index(self) -> None:
        """Rebuild the keyword index."""
        self._index.clear()
        for idx, mem in enumerate(self._memories):
            for kw in mem._keywords_en:
                self._index.setdefault(kw, []).append(idx)
            for kw in mem._keywords_cjk:
                self._index.setdefault(kw, []).append(idx)

    def get_all(self, category: Optional[str] = None) -> list[str]:
        """Get all memories, optionally filtered by category."""
        if category:
            return [m.text for m in self._memories if m.category == category]
        return [m.text for m in self._memories]

    def count(self) -> int:
        """Return total number of memories."""
        return len(self._memories)

    def clear(self) -> None:
        """Clear all memories."""
        self._memories.clear()
        self._index.clear()


# ===== Legacy Functions for Backward Compatibility =====

def load_memory_lines(path: str) -> list[str]:
    """Load memory lines from a file (legacy function)."""
    try:
        with open(path, "r", encoding="utf-8") as file:
            lines = [line.strip() for line in file.readlines()]
        return [line for line in lines if line and not line.startswith("#")]
    except FileNotFoundError:
        return []


def select_memory(lines: list[str], message: str, max_lines: int = 4) -> list[str]:
    """Select relevant memories for a message (legacy function)."""
    store = MemoryStore()
    for line in lines:
        store.add(line)
    
    results = store.search(message, max_results=max_lines)
    return [text for text, _, _ in results]
