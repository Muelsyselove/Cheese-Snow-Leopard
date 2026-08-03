"""文档解析 Worker — QThread 后台解析

集成 GPU 信号量：方案B(vlm)/方案C 需 GPU 时通过信号量排队，防 OOM。
"""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from interfaces.parser import DocumentParser
from services.concurrency import GpuSemaphore


class ParseWorker(QThread):
    """文档解析后台 Worker"""
    progress = Signal(int, str)       # (百分比, 消息)
    finished = Signal(list)           # 解析结果（ParsedDocument 列表）
    error = Signal(str)               # 错误信息

    def __init__(self, parser: DocumentParser, file_paths: list[str],
                 gpu_sem: GpuSemaphore = None):
        super().__init__()
        self.parser = parser
        self.file_paths = file_paths
        self.gpu_sem = gpu_sem

    def run(self):
        results = []
        for i, path in enumerate(self.file_paths):
            try:
                self.progress.emit(
                    int(i / len(self.file_paths) * 100),
                    f"正在解析: {path}"
                )
                # GPU 任务通过信号量排队，防 OOM
                if self.parser.requires_gpu and self.gpu_sem:
                    with self.gpu_sem:
                        doc = self.parser.parse_document(path)
                else:
                    doc = self.parser.parse_document(path)  # CPU 任务不抢 GPU
                results.append(doc)
            except Exception as e:
                self.error.emit(str(e))
                return
        self.finished.emit(results)
