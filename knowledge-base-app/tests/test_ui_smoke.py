"""新 UI（液态玻璃 QML）冒烟测试 — offscreen 模式

验证：
1. i18n 服务词典加载与中英文切换
2. 4 个 Bridge 在服务为 None 时可装配（优雅降级）
3. Main.qml 可加载（StackLayout 会实例化全部页面，覆盖所有 QML 文件语法）
4. 无 QML 致命错误

运行：.venv\\Scripts\\python.exe -m pytest tests/test_ui_smoke.py -v
（需要 offscreen 平台，CI/无显示环境可用）
"""
from __future__ import annotations

import os
import sys

try:
    import pytest
except ModuleNotFoundError:  # venv 未装 pytest 时仅支持直接运行入口
    pytest = None

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)


if pytest is not None:
    _fixture = pytest.fixture(scope="module")
else:  # 直接运行时 pytest 不存在，fixture 装饰器退化为恒等
    def _fixture(fn):
        return fn


@_fixture
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


@_fixture
def qml_warnings():
    """捕获 Qt/QML 警告消息"""
    from PySide6.QtCore import qInstallMessageHandler, QtMsgType
    messages: list[str] = []

    def handler(mode, ctx, msg):
        if mode in (QtMsgType.QtWarningMsg, QtMsgType.QtCriticalMsg,
                    QtMsgType.QtFatalMsg):
            messages.append(msg)

    qInstallMessageHandler(handler)
    return messages


@_fixture
def assembled(qapp, qml_warnings):
    """装配 i18n + Bridges + QML 引擎并加载 Main.qml"""
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlApplicationEngine

    from ui_old_v2.i18n import I18nService
    from ui_old_v2.bridges import (
        ChatBridge, FilesBridge, KnowledgeBridge, SettingsBridge,
    )

    i18n = I18nService(config_path="config.yaml", parent=qapp)
    bridges = {
        "chatBridge": ChatBridge(i18n=i18n, parent=qapp),
        "filesBridge": FilesBridge(i18n=i18n, parent=qapp),
        "knowledgeBridge": KnowledgeBridge(i18n=i18n, parent=qapp),
        "settingsBridge": SettingsBridge(i18n=i18n, parent=qapp),
    }

    engine = QQmlApplicationEngine(parent=qapp)
    ctx = engine.rootContext()
    ctx.setContextProperty("i18n", i18n)
    for name, bridge in bridges.items():
        ctx.setContextProperty(name, bridge)
    ctx.setContextProperty("startupErrors", [])

    engine.load(QUrl.fromLocalFile(
        os.path.join(APP_DIR, "ui_old_v2", "qml", "Main.qml")))
    return {"engine": engine, "i18n": i18n, "bridges": bridges}


def test_i18n_dicts_loaded(assembled):
    i18n = assembled["i18n"]
    assert i18n.tr("nav.chat") != "nav.chat"          # zh_CN 默认
    assert i18n.tr("app.title") != "app.title"


def test_i18n_language_switch(assembled):
    i18n = assembled["i18n"]
    i18n.language = "en_US"
    assert i18n.tr("nav.chat") == "Chat"
    i18n.language = "zh_CN"
    assert i18n.tr("nav.chat") == "对话"


def test_i18n_trf_placeholder(assembled):
    i18n = assembled["i18n"]
    text = i18n.trf("files.imported", {"count": 3})
    assert "3" in text


def test_bridges_degrade_gracefully(assembled):
    """服务为 None 时桥接属性返回空而非抛异常"""
    bridges = assembled["bridges"]
    assert bridges["chatBridge"].conversations == []
    assert bridges["chatBridge"].models == []
    assert bridges["filesBridge"].documents == []
    assert bridges["knowledgeBridge"].categories == []
    assert isinstance(bridges["settingsBridge"].providers, list)


def test_main_qml_loads(assembled, qml_warnings):
    engine = assembled["engine"]
    assert engine.rootObjects(), "Main.qml 加载失败"
    critical = [m for m in qml_warnings
                if "is not defined" in m or "Cannot read" in m
                or "Unable to assign" in m or "is not a type" in m]
    assert not critical, "QML 存在引用/类型错误:\n" + "\n".join(critical[:20])


# ---------------------------------------------------------- 直接运行入口
if __name__ == "__main__":
    """venv 无 pytest 时可直接执行：.venv\\Scripts\\python.exe tests/test_ui_smoke.py"""
    os.chdir(APP_DIR)
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import qInstallMessageHandler, QtMsgType, QUrl
    from PySide6.QtQml import QQmlApplicationEngine

    msgs: list[str] = []

    def _handler(mode, ctx, msg):
        tag = {QtMsgType.QtWarningMsg: "WARN",
               QtMsgType.QtCriticalMsg: "CRIT",
               QtMsgType.QtFatalMsg: "FATAL"}.get(mode)
        if tag:
            msgs.append(f"[{tag}] {msg}")

    qInstallMessageHandler(_handler)
    app = QApplication.instance() or QApplication([])

    from ui_old_v2.i18n import I18nService
    from ui_old_v2.bridges import (
        ChatBridge, FilesBridge, KnowledgeBridge, SettingsBridge,
    )

    i18n = I18nService(config_path="config.yaml", parent=app)
    bridges = {
        "chatBridge": ChatBridge(i18n=i18n, parent=app),
        "filesBridge": FilesBridge(i18n=i18n, parent=app),
        "knowledgeBridge": KnowledgeBridge(i18n=i18n, parent=app),
        "settingsBridge": SettingsBridge(i18n=i18n, parent=app),
    }

    engine = QQmlApplicationEngine(parent=app)
    ctx = engine.rootContext()
    ctx.setContextProperty("i18n", i18n)
    for name, bridge in bridges.items():
        ctx.setContextProperty(name, bridge)
    ctx.setContextProperty("startupErrors", [])

    engine.load(QUrl.fromLocalFile(
        os.path.join(APP_DIR, "ui_old_v2", "qml", "Main.qml")))

    failures = 0

    def check(name, fn):
        global failures
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as e:
            failures += 1
            print(f"  FAIL  {name}: {e}")

    check("i18n_dicts", lambda: (_ for _ in ()).throw(AssertionError())
          if i18n.tr("nav.chat") == "nav.chat" else None)

    def _switch():
        i18n.language = "en_US"
        assert i18n.tr("nav.chat") == "Chat", i18n.tr("nav.chat")
        i18n.language = "zh_CN"
        assert i18n.tr("nav.chat") == "对话", i18n.tr("nav.chat")
    check("i18n_switch", _switch)

    def _trf():
        assert "3" in i18n.trf("files.imported", {"count": 3})
    check("i18n_trf", _trf)

    def _degrade():
        assert bridges["chatBridge"].conversations == []
        assert bridges["chatBridge"].models == []
        assert bridges["filesBridge"].documents == []
        assert bridges["knowledgeBridge"].categories == []
        assert isinstance(bridges["settingsBridge"].providers, list)
    check("bridges_degrade", _degrade)

    def _qml():
        assert engine.rootObjects(), "Main.qml 加载失败"
        bad = [m for m in msgs
               if "is not defined" in m or "Cannot read" in m
               or "Unable to assign" in m or "is not a type" in m]
        assert not bad, "\n".join(bad[:20])
    check("main_qml_loads", _qml)

    print(f"\nwarnings/criticals: {len(msgs)}")
    for m in msgs[:40]:
        print("  ", m)
    print("SMOKE TEST", "PASSED" if not failures else f"FAILED ({failures})")
    sys.exit(1 if failures else 0)
