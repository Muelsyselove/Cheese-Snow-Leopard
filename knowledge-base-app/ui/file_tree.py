"""文件目录树 — 展示已导入文档（作为文件页主组件）"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem, QPushButton,
    QFileDialog, QHBoxLayout, QLabel,
)
from PySide6.QtCore import Signal


class FileTree(QWidget):
    """文件目录树"""
    import_requested = Signal(list)   # 用户选择导入文件

    def __init__(self):
        super().__init__()
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # 标题
        title = QLabel("文件管理")
        title.setStyleSheet("font-weight: bold; font-size: 15px;")
        layout.addWidget(title)

        # 操作按钮
        btn_row = QHBoxLayout()
        self.import_btn = QPushButton("+ 导入文件")
        self.import_btn.clicked.connect(self._on_import_click)
        btn_row.addWidget(self.import_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # 文件树
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["文件名", "状态", "页数"])
        self.tree.setColumnWidth(0, 320)
        layout.addWidget(self.tree, 1)

    def _on_import_click(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "选择文件", "",
            "文档 (*.pdf *.docx *.png *.jpg *.txt);;所有文件 (*)"
        )
        if paths:
            self.import_requested.emit(paths)

    def add_document(self, doc):
        """添加文档到树"""
        item = QTreeWidgetItem([
            getattr(doc, "file_name", str(doc)),
            getattr(doc, "parse_status", "completed"),
            str(getattr(doc, "page_count", "") or "")
        ])
        self.tree.addTopLevelItem(item)
