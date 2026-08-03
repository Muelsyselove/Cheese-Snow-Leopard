"""测试配置

PySide6 不可用时注入轻量 stub，使依赖 QThread/Signal 的纯逻辑测试可在无 Qt
环境运行。真实 PySide6 已安装时跳过 stub，使用原生 Qt 信号。

stub 行为：Signal 为同步直连（emit 立即调用已连接 slot），QThread 为普通基类。
"""
from __future__ import annotations

import sys
import types


def _install_pyside6_stub():
    """注入 PySide6.QtCore 轻量 stub（QThread + 同步 Signal）"""
    QtCore = types.ModuleType("PySide6.QtCore")

    class QThread:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            pass

    class _SignalInstance:
        def __init__(self):
            self._slots: list = []

        def connect(self, slot):
            self._slots.append(slot)

        def disconnect(self, slot=None):
            if slot is None:
                self._slots.clear()
            else:
                self._slots = [s for s in self._slots if s is not slot]

        def emit(self, *args):
            for s in list(self._slots):
                s(*args)

    class _SignalDescriptor:
        """非数据描述符：每个实例返回独立 _SignalInstance"""

        def __init__(self, *args, **kwargs):
            self._key = f"_sig_{id(self)}"

        def __get__(self, instance, owner=None):
            if instance is None:
                return self
            sig = instance.__dict__.get(self._key)
            if sig is None:
                sig = _SignalInstance()
                instance.__dict__[self._key] = sig
            return sig

    def Signal(*args, **kwargs):
        return _SignalDescriptor(*args, **kwargs)

    QtCore.QThread = QThread
    QtCore.Signal = Signal

    PySide6 = types.ModuleType("PySide6")
    PySide6.QtCore = QtCore
    PySide6._is_stub = True  # 标记，供 qapp fixture 判断
    sys.modules["PySide6"] = PySide6
    sys.modules["PySide6.QtCore"] = QtCore


try:
    import PySide6  # noqa: F401
except ImportError:
    _install_pyside6_stub()


import pytest


@pytest.fixture(scope="session")
def qapp():
    """会话级 QApplication（真实 PySide6 需要；stub 模式返回 None）"""
    import PySide6
    if getattr(PySide6, "_is_stub", False):
        yield None
        return
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    yield app
