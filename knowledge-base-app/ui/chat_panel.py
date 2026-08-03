"""聊天面板 — 用户提问 + 答案流式渲染"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTextEdit, QLineEdit, QPushButton, QHBoxLayout
)
from PySide6.QtCore import Signal, Slot


class ChatPanel(QWidget):
    """聊天面板"""
    references_ready = Signal(list)   # 引用列表就绪

    def __init__(self, rag_service=None):
        super().__init__()
        self.rag_service = rag_service
        self.history: list[dict] = []
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        # 答案显示区
        self.answer_view = QTextEdit()
        self.answer_view.setReadOnly(True)
        layout.addWidget(self.answer_view)
        # 输入区
        input_row = QHBoxLayout()
        self.input_box = QLineEdit()
        self.input_box.setPlaceholderText("输入问题，回车发送...")
        self.input_box.returnPressed.connect(self._on_send)
        self.send_btn = QPushButton("发送")
        self.send_btn.clicked.connect(self._on_send)
        input_row.addWidget(self.input_box)
        input_row.addWidget(self.send_btn)
        layout.addLayout(input_row)

    @Slot()
    def _on_send(self):
        question = self.input_box.text().strip()
        if not question or not self.rag_service:
            return
        self.answer_view.append(f"<b>你:</b> {question}")
        self.input_box.clear()
        # 启动检索 Worker
        from workers.search_worker import SearchWorker
        self.search_worker = SearchWorker(
            self.rag_service, question, self.history
        )
        self.search_worker.finished.connect(self._on_search_done)
        self.search_worker.error.connect(self._on_search_error)
        self.search_worker.start()

    @Slot(dict)
    def _on_search_done(self, result):
        answer = result["answer"]
        retrieved = result["retrieved_chunks"]
        self.answer_view.append(f"<b>助手:</b> {answer}")
        # 溯源解析
        from services.trace_service import trace_references, trace_references_fallback
        refs = trace_references(answer, retrieved)
        if not refs and retrieved:
            refs = trace_references_fallback(answer, retrieved)
        self.references_ready.emit(refs)
        self.history.append({"role": "user", "content": question})
        self.history.append({"role": "assistant", "content": answer})

    @Slot(str)
    def _on_search_error(self, msg: str):
        self.answer_view.append(f"<i style='color:red'>检索失败: {msg}</i>")
