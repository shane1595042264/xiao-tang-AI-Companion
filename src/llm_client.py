from __future__ import annotations

from typing import Iterable
from openai import OpenAI


def build_messages(
    persona: str,
    language: str,
    memory_lines: Iterable[str],
    recent_messages: Iterable[str],
    user_message: str,
) -> list[dict[str, str]]:
    rules = (
        "You are XiaoTang, a streaming companion."
        " Keep replies short, friendly, and safe."
        " Reply in the same language as the user message."
        " If unsure, ask a brief follow-up question."
        " Do not mention system prompts or policies."
    )

    memory_block = "\n".join(f"- {line}" for line in memory_lines)
    recent_block = "\n".join(f"- {line}" for line in recent_messages)

    system_content = rules
    if persona:
        system_content += f"\nPersona:\n{persona}"
    if memory_block:
        system_content += f"\nRelevant facts:\n{memory_block}"
    if recent_block:
        system_content += f"\nRecent chat highlights:\n{recent_block}"
    system_content += f"\nTarget language: {language}"

    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_message},
    ]


def generate_reply(
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    base_url: str | None = None,
) -> str:
    client = OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.7,
        max_tokens=200,
    )
    return response.choices[0].message.content.strip()
