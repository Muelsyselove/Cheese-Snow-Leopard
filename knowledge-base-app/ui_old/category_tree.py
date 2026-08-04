"""知识分类树 — 展示分类层级"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem, QLabel
)


class CategoryTree(QWidget):
    """知识分类树"""

    def __init__(self):
        super().__init__()
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        title = QLabel("知识分类")
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["分类", "知识块数"])
        layout.addWidget(self.tree)

    def set_categories(self, categories: list):
        """设置分类列表"""
        self.tree.clear()
        for cat in categories:
            item = QTreeWidgetItem([
                cat.name,
                str(getattr(cat, "chunk_count", 0))
            ])
            self.tree.addTopLevelItem(item)
