"""主窗口 — 三栏布局（文件树 + 聊天面板 + 引用面板）"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QSplitter, QStatusBar, QFileDialog,
    QMessageBox
)
from PySide6.QtCore import Slot

from ui.chat_panel import ChatPanel
from ui.reference_panel import ReferencePanel
from ui.file_tree import FileTree
from ui.category_tree import CategoryTree


class MainWindow(QMainWindow):
    """主窗口"""

    def __init__(self, file_service=None, rag_service=None,
                 lifecycle_service=None, config=None):
        super().__init__()
        self.file_service = file_service
        self.rag_service = rag_service
        self.lifecycle_service = lifecycle_service
        self.config = config or {}

        self.setWindowTitle("自主知识库桌面应用")
        self.resize(
            self.config.get("window_width", 1400),
            self.config.get("window_height", 900)
        )

        self._init_ui()
        self._init_status_bar()

    def _init_ui(self):
        central = QWidget()
        layout = QHBoxLayout(central)

        splitter = QSplitter()
        # 左栏：文件目录树 + 知识分类树
        self.file_tree = FileTree()
        self.category_tree = CategoryTree()
        left_splitter = QSplitter()
        left_splitter.setOrientation(0x1)  # Vertical
        left_splitter.addWidget(self.file_tree)
        left_splitter.addWidget(self.category_tree)

        # 中栏：聊天面板
        self.chat_panel = ChatPanel(rag_service=self.rag_service)

        # 右栏：引用面板
        self.reference_panel = ReferencePanel()

        splitter.addWidget(left_splitter)
        splitter.addWidget(self.chat_panel)
        splitter.addWidget(self.reference_panel)
        splitter.setSizes([300, 700, 300])

        layout.addWidget(splitter)
        central.setLayout(layout)
        self.setCentralWidget(central)

        # 信号连接
        self.chat_panel.references_ready.connect(self._on_references_ready)

    def _init_status_bar(self):
        self.statusBar().showMessage("就绪")

    def on_import_files(self, paths: list[str]):
        """UI 线程接收文件导入请求，启动 ParseWorker"""
        if not self.file_service:
            return
        from workers.parse_worker import ParseWorker
        self.worker = ParseWorker(self.file_service.parser, paths)
        self.worker.progress.connect(self._update_progress)
        self.worker.finished.connect(self._on_parse_done)
        self.worker.error.connect(self._show_error)
        self.worker.start()

    @Slot(int, str)
    def _update_progress(self, percent: int, msg: str):
        self.statusBar().showMessage(f"{msg} ({percent}%)")

    @Slot(list)
    def _on_parse_done(self, results):
        for doc in results:
            self.file_tree.add_document(doc)
        self.statusBar().showMessage(f"已导入 {len(results)} 个文档")

    @Slot(str)
    def _show_error(self, msg: str):
        QMessageBox.critical(self, "错误", msg)
        self.statusBar().showMessage("操作失败")

    @Slot(list)
    def _on_references_ready(self, references):
        self.reference_panel.show_references(references)
