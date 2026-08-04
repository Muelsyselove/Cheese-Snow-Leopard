"""文字 LLM API 接口 — 仅纯文本，对接用户自有 API"""
from __future__ import annotations

from typing import Protocol, Generator


class LLMClient(Protocol):
    """文字 LLM API 接口 — OpenAI 兼容协议"""

    def chat(self, messages: list[dict],
             tools: list | None = None) -> dict:
        """同步聊天，返回带 tool_calls 的响应"""
        ...

    def stream_chat(self, messages: list[dict],
                    tools: list | None = None,
                    thinking: bool = True,
                    should_stop=None) -> Generator[tuple[str, str], None, None]:
        """流式聊天，逐 token 返回 (kind, text)。

        kind 取值：
          - "reasoning"  思考过程（reasoning_content）
          - "content"    正式回答内容
          - "tool_call"  text 为 JSON 字符串（工具调用增量）
        """
        ...
