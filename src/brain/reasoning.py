"""Reasoning Engine - Central decision-making and task orchestration."""

from __future__ import annotations

import json
from typing import Any, Callable, Optional

from .llm_client import LLMClient


class ReasoningEngine:
    """
    Central reasoning engine that decides what actions to take.

    This is XiaoTang's "brain" - it processes inputs, decides on actions,
    and can invoke tools/hands to interact with the world.
    """

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm = llm_client
        self._tools: dict[str, Callable] = {}
        self._tool_schemas: list[dict] = []

    def register_tool(
        self,
        name: str,
        func: Callable,
        description: str,
        parameters: dict[str, Any],
    ) -> None:
        """Register a tool that XiaoTang can use."""
        self._tools[name] = func
        self._tool_schemas.append({
            "name": name,
            "description": description,
            "input_schema": parameters,
        })

    async def think_and_act(
        self,
        situation: str,
        context: dict[str, Any],
    ) -> tuple[str, list[dict]]:
        """
        Process a situation, decide on actions, and execute them.

        Returns:
            tuple: (response_text, list_of_actions_taken)
        """
        system_prompt = (
            "You are XiaoTang, an AI assistant that can think and take actions. "
            "Analyze the situation and decide what to do. "
            "You can use tools to interact with the computer and environment."
        )

        messages = [
            {
                "role": "user",
                "content": f"Situation: {situation}\nContext: {json.dumps(context, ensure_ascii=False)}",
            },
        ]

        actions_taken = []

        if self._tool_schemas:
            response, tool_calls = self._llm.generate_with_tools(
                messages=messages,
                tools=self._tool_schemas,
                system=system_prompt,
            )

            if tool_calls:
                for call in tool_calls:
                    tool_name = call["name"]
                    if tool_name in self._tools:
                        try:
                            args = call["arguments"]  # Already a dict from Anthropic
                            result = await self._tools[tool_name](**args)
                            actions_taken.append({
                                "tool": tool_name,
                                "args": args,
                                "result": result,
                            })
                        except Exception as e:
                            actions_taken.append({
                                "tool": tool_name,
                                "error": str(e),
                            })
        else:
            response = self._llm.generate(messages, system=system_prompt)

        return response, actions_taken

    def simple_response(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.7,
    ) -> str:
        """Generate a simple response without tool calling."""
        messages = [
            {"role": "user", "content": user_message},
        ]
        return self._llm.generate(messages, system=system_prompt, temperature=temperature)
