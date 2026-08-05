"""OpenAI 兼容文字 LLM 实现 — 对接用户自有 API"""
from __future__ import annotations

import json
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
             tools: Optional[list] = None,
             thinking: Optional[bool] = None) -> dict:
        """同步聊天，返回带 tool_calls 的响应。失败时按参数退化重试。

        Args:
            tools: langchain BaseTool 列表或 OpenAI 工具字典列表。
                   langchain 工具会自动转换为 OpenAI 格式。
            thinking: None=不特殊指定；True=显式思考；False=显式非思考。
                      当模型不支持某些参数时会自动降级为更简请求重试。
        """
        client = self._get_client()
        last_err = None
        # 将 langchain BaseTool 转换为 OpenAI 工具格式
        openai_tools = self._convert_tools(tools) if tools else None
        # 构造「由完整到最简」的请求变体，逐步去掉可能不被目标模型接受的参数。
        # DeepSeek V4 等思考型模型在非思考模式下常拒绝 temperature / max_tokens /
        # thinking 等字段，依次退化为仅 model + messages，保证调用最终成功。
        variants = self._build_variants(messages, openai_tools, thinking)

        for attempt in range(self.max_retries):
            for kwargs in variants:
                try:
                    resp = client.chat.completions.create(**kwargs)
                    return {
                        "content": resp.choices[0].message.content,
                        "tool_calls": self._convert_tool_calls(resp.choices[0].message.tool_calls),
                        "raw": resp
                    }
                except Exception as e:
                    last_err = e
            # 一轮变体全部失败，指数退避后重试
            wait = 2 ** attempt
            time.sleep(wait)
        raise LLMError(f"LLM 调用失败（重试 {self.max_retries} 次）: {last_err}") from last_err

    def _build_variants(self, messages: list[dict],
                        openai_tools: Optional[list],
                        thinking: Optional[bool]) -> list[dict]:
        """构造由完整到最简的请求参数变体。

        用于应对各家模型对参数的不同约束——某个变体被拒绝时自动尝试去掉
        thinking / temperature / max_tokens 的更简变体。
        """
        base: dict = {"model": self.model, "messages": messages}
        if openai_tools:
            base["tools"] = openai_tools

        # 1) 完整请求
        full = dict(base)
        full["temperature"] = self.temperature
        full["max_tokens"] = self.max_tokens
        if thinking is not None:
            full["extra_body"] = {
                "thinking": {"type": "enabled" if thinking else "disabled"}}
        variants = [full]

        # 2) 去掉思考参数
        v = dict(full)
        v.pop("extra_body", None)
        if v not in variants:
            variants.append(v)

        # 3) 再去掉温度
        v = dict(full)
        v.pop("extra_body", None)
        v.pop("temperature", None)
        if v not in variants:
            variants.append(v)

        # 4) 再去掉 max_tokens
        v = dict(full)
        v.pop("extra_body", None)
        v.pop("temperature", None)
        v.pop("max_tokens", None)
        if v not in variants:
            variants.append(v)

        # 5) 仅保留 model + messages（+ tools）
        v = dict(base)
        if v not in variants:
            variants.append(v)

        return variants

    @staticmethod
    def _convert_tool_calls(tool_calls):
        """将 OpenAI SDK 的 ChatCompletionMessageToolCall 对象转为 langchain ToolCall dict 格式

        langchain 的 AIMessage(tool_calls=...) 期望 list[dict]（含 name/args/id/type），
        而 OpenAI SDK 返回的是对象。args 需从 JSON 字符串反序列化为 dict。
        """
        if not tool_calls:
            return []
        converted = []
        for tc in tool_calls:
            if getattr(tc, "type", None) != "function":
                continue
            fn = getattr(tc, "function", None)
            if fn is None:
                continue
            args = {}
            try:
                import json
                args = json.loads(fn.arguments or "{}")
            except Exception:
                args = {}
            converted.append({
                "name": fn.name,
                "args": args,
                "id": getattr(tc, "id", ""),
                "type": "tool_call",
            })
        return converted

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

    def stream_chat(self, messages: list[dict],
                    tools: Optional[list] = None,
                    thinking: bool = True,
                    thinking_strength: Optional[str] = "auto",
                    should_stop=None) -> Generator[tuple[str, str], None, None]:
        """流式聊天，逐 token 返回 (kind, text)。

        kind:
          - "reasoning"  思考过程（reasoning_content）
          - "content"    正式回答内容
          - "tool_call"  text 为 JSON 字符串（工具调用增量）
        支持 should_stop 回调用于中途中断（返回 True 则停止）。

        thinking_strength: 部分思考模型可调整思维链强度，
            "auto"/"low"/"medium"/"high"（低/中/高）。auto 不传额外参数。
        """
        client = self._get_client()
        openai_tools = self._convert_tools(tools) if tools else None
        kwargs = {
            "model": self.model, "messages": messages,
            "temperature": self.temperature, "max_tokens": self.max_tokens,
            "stream": True,
        }
        if openai_tools:
            kwargs["tools"] = openai_tools
        # 思考开关：仅当显式要求思考时传参（部分模型不支持，失败则忽略）
        if thinking:
            try:
                body = {"thinking": {"type": "enabled"}}
                if thinking_strength and thinking_strength != "auto":
                    # 可思考模型支持调整思维链强度（reasoning_effort 为通用字段）
                    body["reasoning_effort"] = thinking_strength
                kwargs["extra_body"] = body
            except Exception:
                pass

        stream = client.chat.completions.create(**kwargs)
        for chunk in stream:
            if should_stop is not None and should_stop():
                return
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            # 思考过程（仅思考模式开启时展示）
            if thinking:
                reasoning = getattr(delta, "reasoning_content", None)
                if reasoning:
                    yield ("reasoning", reasoning)
            # 工具调用
            if getattr(delta, "tool_calls", None):
                for tc in delta.tool_calls:
                    fn = getattr(tc, "function", None)
                    if fn is not None:
                        yield ("tool_call", json.dumps({
                            "index": tc.index,
                            "id": tc.id,
                            "name": fn.name,
                            "arguments": fn.arguments or "",
                        }, ensure_ascii=False))
            # 正式回答
            content = getattr(delta, "content", None)
            if content:
                yield ("content", content)
