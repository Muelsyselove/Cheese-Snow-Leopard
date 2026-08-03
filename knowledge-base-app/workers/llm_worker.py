"""LLM 调用 Worker — 流式输出 / 直接对话 / 标题生成"""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from interfaces.llm import LLMClient


class LlmWorker(QThread):
    """LLM 流式调用后台 Worker"""
    token_stream = Signal(str)        # 逐 token 输出
    finished = Signal(str)            # 完整答案
    error = Signal(str)

    def __init__(self, llm: LLMClient, messages: list[dict]):
        super().__init__()
        self.llm = llm
        self.messages = messages

    def run(self):
        try:
            full = ""
            for token in self.llm.stream_chat(self.messages):
                full += token
                self.token_stream.emit(token)
            self.finished.emit(full)
        except Exception as e:
            self.error.emit(str(e))


class DirectChatWorker(QThread):
    """直接 LLM 对话（非 RAG），同步返回完整答案"""
    finished = Signal(str)            # 完整答案
    error = Signal(str)

    def __init__(self, llm: LLMClient, messages: list[dict]):
        super().__init__()
        self.llm = llm
        self.messages = messages

    def run(self):
        try:
            resp = self.llm.chat(self.messages)
            self.finished.emit(resp.get("content", "") or "")
        except Exception as e:
            self.error.emit(str(e))


class TitleWorker(QThread):
    """用 LLM 为对话生成简短标题"""
    finished = Signal(str)            # 生成的标题
    error = Signal(str)

    def __init__(self, llm: LLMClient, user_msg: str, assistant_msg: str):
        super().__init__()
        self.llm = llm
        self.user_msg = user_msg
        self.assistant_msg = assistant_msg

    def run(self):
        try:
            prompt = (
                "请为以下对话生成一个简短的中文标题（不超过12个字，不要加引号、不要句号）。"
                "只返回标题本身：\n\n"
                f"用户：{self.user_msg[:200]}\n"
                f"助手：{self.assistant_msg[:200]}"
            )
            resp = self.llm.chat([{"role": "user", "content": prompt}])
            title = (resp.get("content", "") or "").strip()
            # 清理可能的引号和换行
            title = title.strip("\"'“”‘’「」""\n ")
            if not title:
                title = "新对话"
            if len(title) > 20:
                title = title[:20]
            self.finished.emit(title)
        except Exception as e:
            self.error.emit(str(e))
