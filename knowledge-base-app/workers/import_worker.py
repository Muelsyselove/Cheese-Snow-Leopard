"""文档导入 Worker — QThread 后台执行完整导入流程

调用 file_service.import_document()，将文件持久化到 MinIO + PostgreSQL，
并完成解析/向量化/分类/入库全流程，确保重启后仍能恢复。
"""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from services.file_service import FileService


class ImportWorker(QThread):
    """文档导入后台 Worker（完整全流程）"""
    progress = Signal(int, str)       # (百分比, 消息)
    finished = Signal(list)           # 成功导入的 Document 列表
    error = Signal(str)               # 单个文件失败信息

    def __init__(self, file_service: FileService, file_paths: list[str]):
        super().__init__()
        self.file_service = file_service
        self.file_paths = file_paths

    def run(self):
        results = []
        total = len(self.file_paths)
        for i, path in enumerate(self.file_paths):
            try:
                base = int(i / total * 100) if total else 0
                # 单个文件内的阶段进度：映射到 [base, next_base)
                next_base = int((i + 1) / total * 100) if total else 100
                span = max(next_base - base, 1)

                def _cb(pct, msg, base=base, span=span):
                    self.progress.emit(
                        base + int((pct / 100) * span),
                        f"{msg}: {path}"
                    )

                self.progress.emit(base, f"正在导入: {path}")
                doc_id = self.file_service.import_document(path, progress_cb=_cb)
                doc = self.file_service.pg.get_document(doc_id)
                if doc:
                    results.append(doc)
                self.progress.emit(next_base, f"已导入: {path}")
            except Exception as e:
                self.error.emit(f"{path}: {e}")
        self.progress.emit(100, "导入完成")
        self.finished.emit(results)