"""检索 Worker"""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from services.rag_service import RagService


class SearchWorker(QThread):
    """Agentic RAG 检索后台 Worker（流式）"""
    progress = Signal(int, str)
    reasoning_stream = Signal(str)    # 思考过程逐 token 输出
    token_stream = Signal(str)        # 正式回答逐 token 输出
    finished = Signal(dict)           # {"answer": str, "retrieved_chunks": set}
    error = Signal(str)

    def __init__(self, rag_service: RagService, question: str,
                 history: list[dict] = None, llm=None, thinking: bool = True):
        super().__init__()
        self.rag = rag_service
        self.question = question
        self.history = history or []
        self.llm = llm
        self.thinking = thinking
        self._cancelled = False

    def cancel(self):
        """请求中断当前生成"""
        self._cancelled = True

    def run(self):
        try:
            self.progress.emit(10, "正在检索知识库")
            answer = ""
            for kind, text in self.rag.stream_query(
                    self.question, self.history, llm=self.llm,
                    thinking=self.thinking,
                    should_stop=lambda: self._cancelled):
                if self._cancelled:
                    break
                if kind == "reasoning":
                    self.reasoning_stream.emit(text)
                elif kind == "content":
                    answer += text
                    self.token_stream.emit(text)
            self.progress.emit(100, "检索完成")
            # 引用来源：同一线程内 stream_query 已写入 last_retrieved_chunks
            retrieved = set(getattr(self.rag, "last_retrieved_chunks", set()))
            self.finished.emit({"answer": answer, "retrieved_chunks": retrieved})
        except Exception as e:
            self.error.emit(str(e))