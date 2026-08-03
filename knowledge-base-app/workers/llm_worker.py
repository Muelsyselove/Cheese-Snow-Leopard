"""LLM 调用 Worker — 流式输出"""
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
