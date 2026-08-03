"""知识库页 — 分类树 + 重建向量库操作"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QLabel, QGroupBox,
    QMessageBox,
)
from PySide6.QtCore import Signal, Slot

from ui.category_tree import CategoryTree


class KnowledgePage(QWidget):
    """知识库管理页 — 分类浏览 + 重建向量库"""

    # 转发重建请求给主窗口
    rebuild_requested = Signal()

    def __init__(self, lifecycle_service=None, parent=None):
        super().__init__(parent)
        self.lifecycle_service = lifecycle_service
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        title = QLabel("知识库")
        title.setStyleSheet("font-weight: bold; font-size: 15px;")
        layout.addWidget(title)

        # 分类树
        self.category_tree = CategoryTree()
        layout.addWidget(self.category_tree, 1)

        # 向量库操作区
        ops_group = QGroupBox("向量库维护")
        ops_v = QVBoxLayout(ops_group)
        hint = QLabel(
            "切换 Embedding 模型后，需全量重编码所有知识块。\n"
            "重建期间可继续检索旧向量库。"
        )
        hint.setStyleSheet("color: #666; font-size: 12px;")
        hint.setWordWrap(True)
        ops_v.addWidget(hint)

        self.rebuild_btn = QPushButton("重建向量库")
        self.rebuild_btn.clicked.connect(self._on_rebuild_clicked)
        ops_v.addWidget(self.rebuild_btn)

        layout.addWidget(ops_group)

    @Slot()
    def _on_rebuild_clicked(self):
        if not self.lifecycle_service:
            QMessageBox.warning(self, "提示", "生命周期服务未装配，无法重建")
            return
        reply = QMessageBox.question(
            self, "重建向量库",
            "将全量重编码所有知识块，期间可继续检索旧向量库。\n是否继续？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        # 转发给主窗口统一处理（与状态栏联动）
        self.rebuild_requested.emit()
