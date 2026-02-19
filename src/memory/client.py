"""
Memory Client - MCP-style tool chain for semantic memory retrieval.

This provides a high-level interface for XiaoTang to:
- Store new memories/facts
- Retrieve relevant memories by semantic similarity
- Manage different types of knowledge (persona, facts, conversations)
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .store import MemoryStore


class MemoryClient:
    """
    MCP-style memory client for XiaoTang.
    
    Provides tool chains that the LLM can call to:
    - remember: Store new information
    - recall: Retrieve relevant memories
    - forget: Remove specific memories
    - reflect: Summarize and consolidate memories
    """

    def __init__(self, knowledge_dir: str = "src/memory/knowledge") -> None:
        self._knowledge_dir = Path(knowledge_dir)
        self._knowledge_dir.mkdir(parents=True, exist_ok=True)
        
        self._store = MemoryStore()
        self._conversation_history: list[dict] = []
        
        # Load existing knowledge files
        self._load_knowledge()

    def _load_knowledge(self) -> None:
        """Load all knowledge files into the memory store."""
        for file_path in self._knowledge_dir.glob("*.txt"):
            category = file_path.stem
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        self._store.add(line, category=category)

        for file_path in self._knowledge_dir.glob("*.json"):
            category = file_path.stem
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, str):
                            self._store.add(item, category=category)
                        elif isinstance(item, dict) and "text" in item:
                            self._store.add(item["text"], category=category, metadata=item)

    # ===== Tool Chain Methods (callable by LLM) =====

    async def remember(
        self,
        fact: str,
        category: str = "learned",
        importance: int = 5,
    ) -> dict:
        """
        Store a new fact or piece of information.
        
        Args:
            fact: The information to remember
            category: Type of memory (persona, learned, conversation, etc.)
            importance: How important this is (1-10)
            
        Returns:
            Status of the operation
        """
        self._store.add(
            fact,
            category=category,
            metadata={"importance": importance, "timestamp": datetime.now().isoformat()},
        )
        
        # Persist to file if important enough
        if importance >= 7:
            self._persist_to_file(fact, category)
        
        return {
            "status": "remembered",
            "fact": fact[:100],
            "category": category,
        }

    async def recall(
        self,
        query: str,
        max_results: int = 5,
        category: Optional[str] = None,
        min_score: float = 0.3,
    ) -> list[dict]:
        """
        Retrieve relevant memories based on a query.
        
        Args:
            query: What to search for
            max_results: Maximum number of results
            category: Optional filter by category
            min_score: Minimum relevance score (0-1)
            
        Returns:
            List of relevant memories with scores
        """
        results = self._store.search(
            query,
            max_results=max_results,
            category=category,
        )
        
        return [
            {
                "text": text,
                "score": score,
                "category": meta.get("category", "unknown"),
            }
            for text, score, meta in results
            if score >= min_score
        ]

    async def recall_text(
        self,
        query: str,
        max_results: int = 4,
    ) -> list[str]:
        """
        Simple recall that returns just the text (for backward compatibility).
        """
        results = await self.recall(query, max_results=max_results)
        return [r["text"] for r in results]

    async def forget(self, fact: str) -> dict:
        """Remove a specific memory."""
        removed = self._store.remove(fact)
        return {"status": "forgotten" if removed else "not_found", "fact": fact[:50]}

    async def reflect(self, topic: str) -> dict:
        """
        Reflect on memories about a topic and generate a summary.
        
        This can be used to consolidate many small memories into
        higher-level understanding.
        """
        memories = await self.recall(topic, max_results=10)
        
        return {
            "topic": topic,
            "memory_count": len(memories),
            "memories": memories,
            "summary": f"Found {len(memories)} memories related to '{topic}'",
        }

    async def get_recent_context(self, n: int = 10) -> list[dict]:
        """Get recent conversation history."""
        return self._conversation_history[-n:]

    def add_to_conversation(self, role: str, content: str, username: str = "") -> None:
        """Add a message to conversation history."""
        self._conversation_history.append({
            "role": role,
            "content": content,
            "username": username,
            "timestamp": datetime.now().isoformat(),
        })
        
        # Keep conversation history bounded
        if len(self._conversation_history) > 100:
            self._conversation_history = self._conversation_history[-50:]

    def _persist_to_file(self, fact: str, category: str) -> None:
        """Persist an important fact to a file."""
        file_path = self._knowledge_dir / f"{category}.txt"
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(f"{fact}\n")

    # ===== Tool Schemas for LLM =====

    @staticmethod
    def get_tool_schemas() -> list[dict]:
        """Return OpenAI-format tool schemas for memory operations."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "remember",
                    "description": "Store a new fact or piece of information in memory",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "fact": {
                                "type": "string",
                                "description": "The information to remember",
                            },
                            "category": {
                                "type": "string",
                                "enum": ["persona", "learned", "user_info", "preference"],
                                "description": "Category of the memory",
                            },
                            "importance": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 10,
                                "description": "How important (1-10). 7+ gets persisted.",
                            },
                        },
                        "required": ["fact"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "recall",
                    "description": "Search memory for relevant information",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "What to search for",
                            },
                            "max_results": {
                                "type": "integer",
                                "default": 5,
                                "description": "Maximum results to return",
                            },
                            "category": {
                                "type": "string",
                                "description": "Optional category filter",
                            },
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "reflect",
                    "description": "Reflect on and summarize memories about a topic",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "topic": {
                                "type": "string",
                                "description": "Topic to reflect on",
                            },
                        },
                        "required": ["topic"],
                    },
                },
            },
        ]
