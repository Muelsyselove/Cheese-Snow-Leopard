"""OpenAI 兼容文字 LLM 实现 — 对接用户自有 API"""
from __future__ import annotations

import time
from typing import Generator, Optional

from interfaces.llm import LLMClient
from utils.exceptions import LLMError


class OpenAILLMClient:
    """OpenAI 兼容协议 LLM 实现"""

    def __init__(self, api_base: str, api_key: str, model: str = "gpt-4o",
                 temperature: float = 0.3, max_tokens: int = 4096,
                 timeout: int = 60, max_retries: int = 3):
        self.api_base = api_base
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.max_retries = max_retries
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(
                base_url=self.api_base,
                api_key=self.api_key,
                timeout=self.timeout
            )
        return self._client

    def chat(self, messages: list[dict],
             tools: Optional[list] = None) -> dict:
        """同步聊天，返回带 tool_calls 的响应。失败时指数退避重试。"""
        client = self._get_client()
        last_err = None
        for attempt in range(self.max_retries):
            try:
                kwargs = {"model": self.model, "messages": messages,
                          "temperature": self.temperature,
                          "max_tokens": self.max_tokens}
                if tools:
                    kwargs["tools"] = tools
                resp = client.chat.completions.create(**kwargs)
                return {
                    "content": resp.choices[0].message.content,
                    "tool_calls": resp.choices[0].message.tool_calls,
                    "raw": resp
                }
            except Exception as e:
                last_err = e
                # 指数退避
                wait = 2 ** attempt
                time.sleep(wait)
        raise LLMError(f"LLM 调用失败（重试 {self.max_retries} 次）: {last_err}") from last_err

    def stream_chat(self, messages: list[dict]) -> Generator[str, None, None]:
        """流式聊天，逐 token 返回"""
        client = self._get_client()
        stream = client.chat.completions.create(
            model=self.model, messages=messages,
            temperature=self.temperature, max_tokens=self.max_tokens,
            stream=True
        )
        for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
