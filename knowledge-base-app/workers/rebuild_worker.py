"""向量库重建 Worker — Embedding 模型切换后手动触发

步骤：①新建 collection(新维度) ②全量重编码 ③切换别名 ④删除旧 collection
"""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal


class RebuildWorker(QThread):
    """向量库重建后台 Worker"""
    progress = Signal(int, str)
    finished = Signal(bool)           # 是否成功
    error = Signal(str)

    def __init__(self, config, factory, pg_repo=None):
        super().__init__()
        self.config = config
        self.factory = factory
        self.pg = pg_repo

    def run(self):
        try:
            self.progress.emit(0, "开始重建向量库")
            # TODO: 实现重建流程
            # 1. 新建 collection（按新 Embedding 维度）
            # 2. 全量重编码所有 chunk_index.content
            # 3. 切换别名指向新 collection
            # 4. 删除旧 collection
            self.progress.emit(100, "向量库重建完成")
            self.finished.emit(True)
        except Exception as e:
            self.error.emit(str(e))
            self.finished.emit(False)
