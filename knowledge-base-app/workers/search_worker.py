"""检索 Worker"""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from services.rag_service import RagService


class SearchWorker(QThread):
    """Agentic RAG 检索后台 Worker"""
    progress = Signal(int, str)
    finished = Signal(dict)           # {"answer": str, "retrieved_chunks": set}
    error = Signal(str)

    def __init__(self, rag_service: RagService, question: str,
                 history: list[dict] = None, llm=None):
        super().__init__()
        self.rag = rag_service
        self.question = question
        self.history = history or []
        self.llm = llm

    def run(self):
        try:
            self.progress.emit(10, "正在检索知识库")
            result = self.rag.query(self.question, self.history, llm=self.llm)
            self.progress.emit(100, "检索完成")
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))
