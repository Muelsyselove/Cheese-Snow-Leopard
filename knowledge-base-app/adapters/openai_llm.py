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
        """同步聊天，返回带 tool_calls 的响应。失败时指数退避重试。

        Args:
            tools: langchain BaseTool 列表或 OpenAI 工具字典列表。
                   langchain 工具会自动转换为 OpenAI 格式。
        """
        client = self._get_client()
        last_err = None
        # 将 langchain BaseTool 转换为 OpenAI 工具格式
        openai_tools = self._convert_tools(tools) if tools else None
        for attempt in range(self.max_retries):
            try:
                kwargs = {"model": self.model, "messages": messages,
                          "temperature": self.temperature,
                          "max_tokens": self.max_tokens}
                if openai_tools:
                    kwargs["tools"] = openai_tools
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

    @staticmethod
    def _convert_tools(tools: list) -> list[dict]:
        """将 langchain BaseTool 转换为 OpenAI 工具格式

        OpenAI SDK 无法直接序列化 langchain 工具对象（含 pydantic ModelMetaclass），
        需先转换为 {"type": "function", "function": {...}} 字典格式。
        """
        converted = []
        for t in tools:
            # 已经是 OpenAI 字典格式
            if isinstance(t, dict) and ("function" in t or "type" in t):
                converted.append(t)
                continue
            # langchain BaseTool / StructuredTool
            if hasattr(t, "name") and hasattr(t, "description") and hasattr(t, "args_schema"):
                try:
                    from langchain_core.utils.function_calling import (
                        convert_to_openai_tool,
                    )
                    converted.append(convert_to_openai_tool(t))
                    continue
                except Exception:
                    pass
                # 手动构建 schema 兜底
                schema = {}
                if t.args_schema is not None:
                    try:
                        schema = t.args_schema.model_json_schema()
                    except Exception:
                        schema = {}
                converted.append({
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description or "",
                        "parameters": schema or {"type": "object", "properties": {}},
                    },
                })
            else:
                # 未知类型，原样传递（让 OpenAI SDK 自行处理或报错）
                converted.append(t)
        return converted

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
