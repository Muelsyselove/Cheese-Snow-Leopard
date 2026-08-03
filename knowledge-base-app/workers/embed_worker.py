"""向量化 Worker"""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from interfaces.embedder import Embedder


class EmbedWorker(QThread):
    """向量化后台 Worker"""
    progress = Signal(int, str)
    finished = Signal(list)           # EmbeddingResult 列表
    error = Signal(str)

    def __init__(self, embedder: Embedder, texts: list[str]):
        super().__init__()
        self.embedder = embedder
        self.texts = texts

    def run(self):
        try:
            self.progress.emit(0, "开始向量化")
            results = self.embedder.encode(self.texts)
            self.progress.emit(100, f"已完成 {len(results)} 条向量化")
            self.finished.emit(results)
        except Exception as e:
            self.error.emit(str(e))
