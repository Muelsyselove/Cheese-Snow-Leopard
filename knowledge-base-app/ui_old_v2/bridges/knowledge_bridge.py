"""知识库页桥接层 — 分类列表 / 向量库重建"""
from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Property, Signal, Slot

logger = logging.getLogger(__name__)


class KnowledgeBridge(QObject):
    """知识库页桥接 — 复刻旧 KnowledgePage + MainWindow 重建逻辑"""

    categoriesChanged = Signal()
    rebuildingChanged = Signal()
    rebuildProgress = Signal(int, str)             # percent, message
    rebuildFinishedOk = Signal(bool)               # 重建完成（成功/失败）
    infoMessage = Signal(str)
    errorMessage = Signal(str)
    statusMessage = Signal(str)

    def __init__(self, lifecycle_service=None, pg_repo=None, i18n=None,
                 parent=None):
        super().__init__(parent)
        self.lifecycle_service = lifecycle_service
        self.pg_repo = pg_repo
        self._i18n = i18n
        self._rebuild_worker = None
        self._rebuilding = False

    def _tr(self, key: str, **params) -> str:
        if self._i18n is None:
            return key
        return self._i18n.trf(key, params) if params else self._i18n.tr(key)

    # ---------------------------------------------------------- 属性
    @Property("QVariantList", notify=categoriesChanged)
    def categories(self) -> list[dict]:
        if self.pg_repo is None:
            return []
        try:
            cats = self.pg_repo.list_all_categories()
        except Exception as e:
            logger.warning(f"加载分类失败: {e}")
            return []
        return [
            {"name": getattr(c, "name", str(c)),
             "chunkCount": int(getattr(c, "chunk_count", 0) or 0)}
            for c in cats
        ]

    @Property(bool, notify=rebuildingChanged)
    def rebuilding(self) -> bool:
        return self._rebuilding

    # ---------------------------------------------------------- 操作
    @Slot()
    def refresh(self):
        self.categoriesChanged.emit()

    @Slot()
    def rebuild(self):
        """执行向量库重建（确认框由 QML 负责）"""
        if self.lifecycle_service is None:
            self.infoMessage.emit(self._tr("knowledge.lifecycleNotReady"))
            return
        if self._rebuilding:
            return
        try:
            worker = self.lifecycle_service.rebuild_vector_store()
        except Exception as e:
            self.errorMessage.emit(self._tr("knowledge.rebuildStartFailed", msg=e))
            return

        self._rebuild_worker = worker
        worker.progress.connect(self._on_progress)
        worker.finished.connect(self._on_finished)
        worker.error.connect(self._on_error)
        self._rebuilding = True
        self.rebuildingChanged.emit()
        worker.start()
        self.statusMessage.emit(self._tr("knowledge.rebuildStarted"))

    def _on_progress(self, percent: int, msg: str):
        self.rebuildProgress.emit(percent, msg)
        self.statusMessage.emit(f"{msg} ({percent}%)")

    def _on_finished(self, success: bool):
        self._rebuilding = False
        self.rebuildingChanged.emit()
        self._rebuild_worker = None
        self.rebuildFinishedOk.emit(success)
        self.statusMessage.emit(
            self._tr("knowledge.rebuildDone") if success
            else self._tr("knowledge.rebuildFailed")
        )

    def _on_error(self, msg: str):
        self._rebuilding = False
        self.rebuildingChanged.emit()
        self._rebuild_worker = None
        self.errorMessage.emit(msg)
