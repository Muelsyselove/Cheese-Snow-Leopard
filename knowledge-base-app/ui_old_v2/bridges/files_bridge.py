"""文件页桥接层 — 文档列表 / 导入 / 删除"""
from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Property, Signal, Slot

logger = logging.getLogger(__name__)


class FilesBridge(QObject):
    """文件页桥接 — 复刻旧 FileTree + MainWindow 导入/删除逻辑"""

    documentsChanged = Signal()
    importProgress = Signal(int, str)              # percent, message
    importRunningChanged = Signal()
    infoMessage = Signal(str)                      # toast
    errorMessage = Signal(str)                     # toast（错误）
    statusMessage = Signal(str)                    # 状态栏

    def __init__(self, file_service=None, lifecycle_service=None,
                 i18n=None, parent=None):
        super().__init__(parent)
        self.file_service = file_service
        self.lifecycle_service = lifecycle_service
        self._i18n = i18n
        self._import_worker = None
        self._import_running = False

    def _tr(self, key: str, **params) -> str:
        if self._i18n is None:
            return key
        return self._i18n.trf(key, params) if params else self._i18n.tr(key)

    # ---------------------------------------------------------- 属性
    @Property("QVariantList", notify=documentsChanged)
    def documents(self) -> list[dict]:
        if self.file_service is None:
            return []
        try:
            docs = self.file_service.list_documents()
        except Exception as e:
            logger.warning(f"加载已导入文档失败: {e}")
            return []
        return [self._doc_to_dict(d) for d in docs]

    @Property(bool, notify=importRunningChanged)
    def importRunning(self) -> bool:
        return self._import_running

    @staticmethod
    def _doc_to_dict(doc) -> dict:
        status = getattr(doc, "parse_status", "completed") or "completed"
        return {
            "docId": getattr(doc, "doc_id", None) or -1,
            "fileName": getattr(doc, "file_name", str(doc)),
            "status": status,
            "statusKey": f"files.status.{status}",
            "pageCount": str(getattr(doc, "page_count", "") or ""),
        }

    # ---------------------------------------------------------- 操作
    @Slot()
    def refresh(self):
        self.documentsChanged.emit()

    @Slot()
    def importFiles(self):
        """弹出文件选择框并启动导入 Worker"""
        if self.file_service is None:
            self.infoMessage.emit(self._tr("files.serviceNotReady"))
            return
        if self._import_running:
            return
        from PySide6.QtWidgets import QFileDialog
        paths, _ = QFileDialog.getOpenFileNames(
            None, self._tr("files.chooseFiles"), "",
            self._tr("files.filter"),
        )
        if not paths:
            return

        from workers.import_worker import ImportWorker
        self._import_worker = ImportWorker(self.file_service, paths)
        self._import_worker.progress.connect(self._on_import_progress)
        self._import_worker.finished.connect(self._on_import_done)
        self._import_worker.error.connect(self._on_import_error)
        self._import_running = True
        self.importRunningChanged.emit()
        self._import_worker.start()

    @Slot(int)
    def deleteDocument(self, doc_id: int):
        """删除文档（确认框由 QML 负责）"""
        if self.lifecycle_service is None:
            self.infoMessage.emit(self._tr("files.lifecycleNotReady"))
            return
        try:
            self.lifecycle_service.delete_document(doc_id)
            self.statusMessage.emit(self._tr("files.deleteQueued"))
            # 乐观移除（异步清理在后台执行）
            self.documentsChanged.emit()
        except Exception as e:
            logger.error(f"删除文档失败 doc_id={doc_id}: {e}", exc_info=True)
            self.errorMessage.emit(self._tr("files.deleteFailed", msg=e))

    # ---------------------------------------------------------- 导入回调
    def _on_import_progress(self, percent: int, msg: str):
        self.importProgress.emit(percent, msg)
        self.statusMessage.emit(f"{msg} ({percent}%)")

    def _on_import_done(self, results: list):
        self._import_running = False
        self.importRunningChanged.emit()
        self._import_worker = None
        self.documentsChanged.emit()
        self.statusMessage.emit(self._tr("files.imported", count=len(results)))

    def _on_import_error(self, msg: str):
        self.errorMessage.emit(msg)
        self.statusMessage.emit(self._tr("status.failed"))
