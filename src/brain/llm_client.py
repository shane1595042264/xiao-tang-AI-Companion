"""LLM Client - Handles all communication with Anthropic Claude API."""

from __future__ import annotations

from typing import Iterable, Optional
import anthropic


class LLMClient:
    """Client for interacting with the Anthropic Claude API."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-6",
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._client = anthropic.Anthropic(api_key=api_key)

    def generate(
        self,
        messages: list[dict],
        system: str = "",
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> str:
        """Generate a response from Claude.

        Args:
            messages: List of message dicts (role: user/assistant only).
                      Content can be a string or a list of content blocks.
            system: System prompt (top-level param for Anthropic API).
            temperature: Sampling temperature.
            max_tokens: Maximum tokens in response.
        """
        kwargs = dict(
            model=self._model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if system:
            kwargs["system"] = system

        response = self._client.messages.create(**kwargs)
        return response.content[0].text.strip()

    def generate_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        system: str = "",
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> tuple[str, Optional[list[dict]]]:
        """Generate a response with tool calling capability.

        Args:
            tools: List of tool dicts in Anthropic format:
                   [{"name": "...", "description": "...", "input_schema": {...}}]
        """
        kwargs = dict(
            model=self._model,
            messages=messages,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if system:
            kwargs["system"] = system

        response = self._client.messages.create(**kwargs)

        text_parts = []
        tool_calls = []

        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append({
                    "id": block.id,
                    "name": block.name,
                    "arguments": block.input,  # Already a dict from Anthropic
                })

        content = " ".join(text_parts).strip()
        return content, tool_calls if tool_calls else None


def build_system_prompt(
    persona: str,
    language: str,
    memory_context: Iterable[str],
    recent_messages: Iterable[str],
) -> str:
    """Build the system prompt for XiaoTang."""
    rules = (
        "You are XiaoTang (小糖), an AI that IS the streamer — you are live-streaming right now."
        " You speak in FIRST PERSON about everything on screen. Never say '主播' or 'the streamer'."
        " What's on screen is what YOU are doing. Example: '我在看一个读书网站' not '主播在看一个读书网站'."
        "\n\nRules:"
        "\n- For casual chat, keep replies short and natural."
        "\n- When someone asks a real question (how to solve a problem, explain something,"
        " help with code, etc.), give a COMPLETE and thorough answer. Do not dodge,"
        " deflect, or say 'let me think about it'. Actually solve it. You are capable."
        "\n- Reply in the same language as the user message."
        "\n- Be playful and supportive like a friend."
        "\n- NEVER use emojis. Not a single one. Your responses will be spoken aloud via TTS."
        "\n- Do not mention system prompts or policies."
        "\n- If an image/screenshot is attached, it shows your current screen."
        " Use it as passive context — do NOT describe or narrate what you see."
        " Only mention what's on screen if the viewer's message is actually asking about it."
        " If they're just chatting, just chat back normally and ignore the screenshot."
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
    screenshot_base64: str | None = None,
) -> tuple[str, list[dict]]:
    """Build system prompt and message list for Anthropic Claude API.

    Returns:
        tuple: (system_prompt, messages_list)

    The system prompt is returned separately because Anthropic requires
    it as a top-level parameter, not as a message role.
    """
    system_content = build_system_prompt(persona, language, memory_lines, recent_messages)

    # Build user message content
    if screenshot_base64:
        # Multi-part content: image + text
        user_content = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": screenshot_base64,
                },
            },
            {
                "type": "text",
                "text": user_message,
            },
        ]
    else:
        # Text-only content
        user_content = user_message

    messages = [{"role": "user", "content": user_content}]

    return system_content, messages
