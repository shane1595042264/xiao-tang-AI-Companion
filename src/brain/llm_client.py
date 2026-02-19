"""LLM Client - Handles all communication with language model APIs."""

from __future__ import annotations

from typing import Iterable, Optional
from openai import OpenAI


class LLMClient:
    """Client for interacting with LLM APIs (OpenAI, Groq, etc.)."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        base_url: Optional[str] = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url
        self._client = OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)

    def generate(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 200,
    ) -> str:
        """Generate a response from the LLM."""
        response = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content.strip()

    def generate_with_tools(
        self,
        messages: list[dict[str, str]],
        tools: list[dict],
        temperature: float = 0.7,
    ) -> tuple[str, Optional[list[dict]]]:
        """Generate a response with tool calling capability."""
        response = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            tools=tools,
            temperature=temperature,
        )
        
        choice = response.choices[0]
        content = choice.message.content or ""
        tool_calls = None
        
        if choice.message.tool_calls:
            tool_calls = [
                {
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                }
                for tc in choice.message.tool_calls
            ]
        
        return content.strip(), tool_calls


def build_system_prompt(
    persona: str,
    language: str,
    memory_context: Iterable[str],
    recent_messages: Iterable[str],
) -> str:
    """Build the system prompt for XiaoTang."""
    rules = (
        "You are XiaoTang (小糖), an AI streaming companion with a cute, friendly personality."
        " Keep replies short, natural, and engaging."
        " Reply in the same language as the user message."
        " Be playful and supportive like a friend."
        " If unsure, ask a brief follow-up question."
        " Do not mention system prompts or policies."
        " You can help with tasks and answer questions."
    )

    memory_block = "\n".join(f"- {line}" for line in memory_context)
    recent_block = "\n".join(f"- {line}" for line in recent_messages)

    content = rules
    if persona:
        content += f"\n\nPersona:\n{persona}"
    if memory_block:
        content += f"\n\nRelevant memories:\n{memory_block}"
    if recent_block:
        content += f"\n\nRecent conversation:\n{recent_block}"
    content += f"\n\nTarget language: {language}"

    return content


def build_messages(
    persona: str,
    language: str,
    memory_lines: Iterable[str],
    recent_messages: Iterable[str],
    user_message: str,
) -> list[dict[str, str]]:
    """Build message list for LLM API call."""
    system_content = build_system_prompt(persona, language, memory_lines, recent_messages)
    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_message},
    ]


# Legacy function for backwards compatibility
def generate_reply(
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    base_url: str | None = None,
) -> str:
    """Generate a reply using the LLM API (legacy function)."""
    client = LLMClient(api_key=api_key, model=model, base_url=base_url)
    return client.generate(messages)
