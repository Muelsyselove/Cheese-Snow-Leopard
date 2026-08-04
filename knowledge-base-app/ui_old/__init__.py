"""[OLD] 旧版 PySide6 Widgets 桌面 UI（已废弃，不再更新与使用）

本包为旧版界面快照，仅保留作参考：
- 不再由 main.py / 启动脚本加载；
- 不再进行功能更新与维护；
- 新版液态玻璃 UI 位于 ui/ 包（PySide6 QtQuick/QML 实现）。
"""
from ui_old.main_window import MainWindow

__all__ = ["MainWindow"]
