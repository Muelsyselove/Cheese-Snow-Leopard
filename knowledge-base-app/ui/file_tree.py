"""文件目录树 — 展示已导入文档（作为文件页主组件）"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem, QPushButton,
    QFileDialog, QHBoxLayout, QLabel, QMessageBox,
)
from PySide6.QtCore import Signal, Qt

from models.document import PARSE_STATUS


def _status_text(status: str) -> str:
    """将 parse_status 转换为中文显示，未识别状态原样返回"""
    return PARSE_STATUS.get(status, status)


class FileTree(QWidget):
    """文件目录树"""
    import_requested = Signal(list)   # 用户选择导入文件
    delete_requested = Signal(int)    # 用户请求删除某文档（doc_id）

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
        self.delete_btn = QPushButton("删除文件")
        self.delete_btn.setEnabled(False)
        self.delete_btn.clicked.connect(self._on_delete_click)
        btn_row.addWidget(self.delete_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # 文件树
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["文件名", "状态", "页数"])
        self.tree.setColumnWidth(0, 320)
        self.tree.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self.tree, 1)

    def _on_import_click(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "选择文件", "",
            "文档 (*.pdf *.docx *.png *.jpg *.jpeg *.txt *.md *.markdown);;所有文件 (*)"
        )
        if paths:
            self.import_requested.emit(paths)

    def _on_selection_changed(self):
        """选中变化时启用/禁用删除按钮"""
        self.delete_btn.setEnabled(len(self.tree.selectedItems()) > 0)

    def _on_delete_click(self):
        items = self.tree.selectedItems()
        if not items:
            return
        item = items[0]
        doc_id = item.data(0, Qt.UserRole)
        name = item.text(0)
        ret = QMessageBox.question(
            self, "确认删除",
            f"确定要删除文件「{name}」吗？\n此操作将删除其向量、分类与原始文件，且不可恢复。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if ret == QMessageBox.Yes and doc_id is not None:
            self.delete_requested.emit(doc_id)
            self.tree.takeTopLevelItem(self.tree.indexOfTopLevelItem(item))

    def add_document(self, doc):
        """添加文档到树"""
        item = QTreeWidgetItem([
            getattr(doc, "file_name", str(doc)),
            _status_text(getattr(doc, "parse_status", "completed")),
            str(getattr(doc, "page_count", "") or "")
        ])
        # 保存 doc_id 供删除使用
        item.setData(0, Qt.UserRole, getattr(doc, "doc_id", None))
        self.tree.addTopLevelItem(item)

    def update_document_status(self, doc_id: int, status: str):
        """按 doc_id 更新对应树节点的状态显示"""
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            if item.data(0, Qt.UserRole) == doc_id:
                item.setText(1, _status_text(status))
                return
