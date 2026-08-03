"""引用面板 — 显示溯源引用列表"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QListWidget, QListWidgetItem, QLabel
)


class ReferencePanel(QWidget):
    """引用面板 — 展示答案中引用的知识块来源"""

    def __init__(self):
        super().__init__()
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        title = QLabel("引用来源")
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title)
        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget)

    def show_references(self, references: list):
        """展示引用列表"""
        self.list_widget.clear()
        if not references:
            item = QListWidgetItem("（无引用）")
            self.list_widget.addItem(item)
            return
        for ref in references:
            text = (
                f"[{ref.get('chunk_id', '')}] "
                f"{ref.get('source_file', '未知文件')} "
                f"第 {ref.get('page', '?')} 页 "
                f"({ref.get('type', 'text')})"
            )
            item = QListWidgetItem(text)
            tooltip = ref.get("excerpt", "")
            if tooltip:
                item.setToolTip(tooltip[:300])
            self.list_widget.addItem(item)
