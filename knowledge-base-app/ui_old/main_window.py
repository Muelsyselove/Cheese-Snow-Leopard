"""主窗口 — 左侧栏按钮切换 + 右侧页面（初始展示对话页）

布局：
+--------+--------------------------+
| 侧边栏 |  右侧页面（QStackedWidget） |
| 对话   |  ┌──────────────────────┐ |
| 文件   |  │  当前页内容           │ |
| 知识库 |  │                      │ |
| 设置   |  └──────────────────────┘ |
+--------+--------------------------+

不使用顶部菜单栏（用户要求）。
"""
from __future__ import annotations

import logging

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QPushButton,
    QStackedWidget, QMessageBox, QFrame,
)
from PySide6.QtCore import Slot, Qt

from ui_old.chat_panel import ChatPanel
from ui_old.file_tree import FileTree
from ui_old.knowledge_page import KnowledgePage

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """主窗口 — 侧边栏导航 + 页面切换"""

    def __init__(self, file_service=None, rag_service=None,
                 lifecycle_service=None, config=None,
                 model_config_service=None, chat_store=None):
        super().__init__()
        self.file_service = file_service
        self.rag_service = rag_service
        self.lifecycle_service = lifecycle_service
        self.config = config or {}
        # 持有 worker 引用避免被 GC
        self._rebuild_worker = None
        self._parse_worker = None

        # 模型配置服务与对话存储
        from services.model_config_service import ModelConfigService
        from services.chat_store import ChatStore
        self.model_config_service = model_config_service or ModelConfigService()
        self.chat_store = chat_store or ChatStore()

        self.setWindowTitle("自主知识库桌面应用")
        self.resize(
            self.config.get("window_width", 1200),
            self.config.get("window_height", 800)
        )

        self._init_ui()
        self._init_status_bar()
        # 默认显示对话页
        self._switch_to(0)

    # ------------------------------------------------------------------ UI
    def _init_ui(self):
        central = QWidget()
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ---- 左侧导航栏 ----
        self._sidebar_buttons: list[QPushButton] = []
        sidebar = self._build_sidebar()
        main_layout.addWidget(sidebar)

        # ---- 右侧页面栈 ----
        self.pages = QStackedWidget()
        main_layout.addWidget(self.pages, 1)

        # 页面 0：对话
        self.chat_panel = ChatPanel(
            rag_service=self.rag_service,
            model_config_service=self.model_config_service,
            chat_store=self.chat_store,
        )
        self.pages.addWidget(self.chat_panel)

        # 页面 1：文件
        self.file_tree = FileTree()
        self.file_tree.import_requested.connect(self.on_import_files)
        self.file_tree.delete_requested.connect(self.on_delete_file)
        self.pages.addWidget(self.file_tree)
        # 启动时从数据库恢复已导入文档
        self._load_existing_documents()

        # 页面 2：知识库
        self.knowledge_page = KnowledgePage(
            lifecycle_service=self.lifecycle_service
        )
        self.knowledge_page.rebuild_requested.connect(self._do_rebuild)
        self.pages.addWidget(self.knowledge_page)

        # 页面 3：设置（懒加载，避免启动时即加载对话框资源）
        self._settings_widget: QWidget | None = None
        # 占位空 widget，首次切换时实例化 SettingsDialog 内容
        self._settings_placeholder = QWidget()
        self.pages.addWidget(self._settings_placeholder)

        self.setCentralWidget(central)

    def _build_sidebar(self) -> QWidget:
        """构建左侧导航栏"""
        sidebar = QFrame()
        sidebar.setFixedWidth(140)
        sidebar.setStyleSheet(
            "QFrame { background: #2c3e50; }"
            "QPushButton {"
            "  color: #ecf0f1; background: transparent; border: none;"
            "  text-align: left; padding: 14px 16px;"
            "  font-size: 14px;"
            "}"
            "QPushButton:hover { background: #34495e; }"
            "QPushButton:checked { background: #1abc9c; color: white; }"
        )
        v = QVBoxLayout(sidebar)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        # 应用标题
        title = QPushButton("📚 知识库")
        title.setEnabled(False)
        title.setStyleSheet(
            "QPushButton { color: #bdc3c7; font-size: 15px; "
            "font-weight: bold; padding: 18px 16px; }"
        )
        v.addWidget(title)

        labels = ["💬 对话", "📁 文件", "🏷️ 知识库", "⚙️ 设置"]
        for i, text in enumerate(labels):
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.setAutoExclusive(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, idx=i: self._switch_to(idx))
            self._sidebar_buttons.append(btn)
            v.addWidget(btn)

        v.addStretch()
        return sidebar

    def _init_status_bar(self):
        self.statusBar().showMessage("就绪")

    # ---------------------------------------------------------- 页面切换
    @Slot(int)
    def _switch_to(self, index: int):
        """切换到指定页面"""
        # 设置页懒加载
        if index == 3 and self._settings_widget is None:
            self._load_settings_page()

        self.pages.setCurrentIndex(index)
        # 同步按钮选中态
        for i, btn in enumerate(self._sidebar_buttons):
            btn.setChecked(i == index)

        # 从设置页切回对话页时，刷新模型下拉框（模型配置可能已变更）
        if index == 0 and self.chat_panel is not None:
            self.model_config_service.load()
            self.chat_panel.refresh_models()

    def _load_settings_page(self):
        """首次切换到设置页时实例化设置界面（嵌入而非对话框）"""
        from ui_old.settings_dialog import SettingsPage
        self._settings_widget = SettingsPage(
            parent=self, model_config_service=self.model_config_service
        )
        self.pages.removeWidget(self._settings_placeholder)
        self._settings_placeholder.deleteLater()
        self._settings_placeholder = None
        self.pages.insertWidget(3, self._settings_widget)

    # ---------------------------------------------------------- 重建向量库
    @Slot()
    def _do_rebuild(self):
        """执行向量库重建（由知识库页转发）"""
        if not self.lifecycle_service:
            QMessageBox.warning(self, "提示", "生命周期服务未装配，无法重建")
            return
        try:
            worker = self.lifecycle_service.rebuild_vector_store()
        except Exception as e:
            QMessageBox.critical(self, "错误", f"启动重建失败: {e}")
            return

        self._rebuild_worker = worker
        worker.progress.connect(self._on_rebuild_progress)
        worker.finished.connect(self._on_rebuild_finished)
        worker.error.connect(self._on_rebuild_error)
        worker.start()
        self.statusBar().showMessage("向量库重建已启动…")

    @Slot(int, str)
    def _on_rebuild_progress(self, percent: int, msg: str):
        self.statusBar().showMessage(f"重建: {msg} ({percent}%)")

    @Slot(bool)
    def _on_rebuild_finished(self, success: bool):
        if success:
            self.statusBar().showMessage("向量库重建完成", 5000)
            QMessageBox.information(self, "完成", "向量库重建完成")
        else:
            self.statusBar().showMessage("向量库重建失败", 5000)
        self._rebuild_worker = None

    @Slot(str)
    def _on_rebuild_error(self, msg: str):
        QMessageBox.critical(self, "重建失败", msg)

    # ---------------------------------------------------------- 文件导入
    def _load_existing_documents(self):
        """启动时从数据库恢复已导入文档到文件树"""
        if not self.file_service:
            return
        try:
            docs = self.file_service.list_documents()
        except Exception as e:
            logger.warning(f"加载已导入文档失败: {e}")
            return
        for doc in docs:
            self.file_tree.add_document(doc)

    def on_import_files(self, paths: list[str]):
        """UI 线程接收文件导入请求，启动 ImportWorker（完整导入流程）"""
        if not self.file_service:
            QMessageBox.information(self, "提示", "文件服务未就绪")
            return
        from workers.import_worker import ImportWorker
        self._parse_worker = ImportWorker(self.file_service, paths)
        self._parse_worker.progress.connect(self._update_progress)
        self._parse_worker.finished.connect(self._on_import_done)
        self._parse_worker.error.connect(self._show_error)
        self._parse_worker.start()

    @Slot(int, str)
    def _update_progress(self, percent: int, msg: str):
        self.statusBar().showMessage(f"{msg} ({percent}%)")

    @Slot(list)
    def _on_import_done(self, results):
        for doc in results:
            self.file_tree.add_document(doc)
        self.statusBar().showMessage(f"已导入 {len(results)} 个文档")

    @Slot(str)
    def _show_error(self, msg: str):
        QMessageBox.critical(self, "错误", msg)
        self.statusBar().showMessage("操作失败")

    @Slot(int)
    def on_delete_file(self, doc_id: int):
        """用户点击删除文档按钮，调用 lifecycle_service 删除"""
        if not self.lifecycle_service:
            QMessageBox.information(self, "提示", "生命周期服务未就绪")
            return
        try:
            self.lifecycle_service.delete_document(doc_id)
            self.statusBar().showMessage(f"文档删除任务已入队，将异步执行清理")
        except Exception as e:
            logger.error(f"删除文档失败 doc_id={doc_id}: {e}", exc_info=True)
            QMessageBox.critical(self, "删除失败", f"删除文档失败: {e}")
