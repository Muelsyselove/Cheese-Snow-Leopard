"""[DEPRECATED old_v2] QML 液态玻璃 UI 装配入口 — 创建桥接层 + QML 引擎

⚠️ 本 UI 系统已标记为 old_v2，不再受系统支持和更新（2026-08-04 起）。
   默认 UI 为 Web 路线（ui_web/ + pywebview WebView2 内核）。
   仅通过 `python main.py --ui=qml` 回退启动。

由 main.py 调用：
    from ui_old_v2.app import run_ui
    exit_code = run_ui(
        file_service=..., rag_service=..., lifecycle_service=...,
        model_config_service=..., chat_store=..., pg_repo=...,
        ui_config=config.ui, startup_errors=[...],
    )

说明：
- QApplication 在此创建（若 main.py 已创建则复用实例）
- 启动错误通过 context property startupErrors 传给 QML，
  由 Main.qml 以玻璃对话框展示（替代旧 QMessageBox）
- 窗口尺寸按屏幕可用区域自适应（不再读取 config.yaml 的 window_width/height）
"""
from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger(__name__)

QML_MAIN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "qml", "Main.qml")


def run_ui(*, file_service=None, rag_service=None, lifecycle_service=None,
           model_config_service=None, chat_store=None, pg_repo=None,
           ui_config: dict | None = None, startup_errors: list[str] | None = None,
           config_path: str = "config.yaml") -> int:
    """装配并启动液态玻璃 UI，返回应用退出码"""
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtWidgets import QApplication

    from ui_old_v2.bridges import (
        ChatBridge, FilesBridge, KnowledgeBridge, SettingsBridge,
    )
    from ui_old_v2.i18n import I18nService
    from ui_old_v2.window_effects import apply_glass_effect

    # 1. QApplication（QtWidgets 版，桥接层文件对话框依赖它）
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Cheese Snow Leopard")

    # 2. 多语言服务 + 桥接层
    i18n = I18nService(config_path=config_path, parent=app)
    chat_bridge = ChatBridge(
        rag_service=rag_service, model_config_service=model_config_service,
        chat_store=chat_store, i18n=i18n, parent=app,
    )
    files_bridge = FilesBridge(
        file_service=file_service, lifecycle_service=lifecycle_service,
        i18n=i18n, parent=app,
    )
    knowledge_bridge = KnowledgeBridge(
        lifecycle_service=lifecycle_service, pg_repo=pg_repo,
        i18n=i18n, parent=app,
    )
    settings_bridge = SettingsBridge(
        model_config_service=model_config_service,
        config_path=config_path, i18n=i18n, parent=app,
    )

    # 3. QML 引擎 + context properties
    engine = QQmlApplicationEngine(parent=app)
    ctx = engine.rootContext()
    ctx.setContextProperty("i18n", i18n)
    ctx.setContextProperty("chatBridge", chat_bridge)
    ctx.setContextProperty("filesBridge", files_bridge)
    ctx.setContextProperty("knowledgeBridge", knowledge_bridge)
    ctx.setContextProperty("settingsBridge", settings_bridge)
    ctx.setContextProperty("startupErrors", list(startup_errors or []))

    # 4. 窗口尺寸：按屏幕可用区域自适应（无任何代码会写回 window_width/height，
    #    config.yaml 中的旧值为手工遗留，故不再读取，始终以屏幕比例计算）
    screen = app.primaryScreen().availableGeometry()
    # 目标占屏幕约 62% 宽 / 72% 高，限制在 [最小尺寸, 最大尺寸] 区间
    width = max(960, min(1440, int(screen.width() * 0.62)))
    height = max(620, min(900, int(screen.height() * 0.72)))
    # 钳制到可用区域内（留边距）
    width = min(width, max(800, screen.width() - 40))
    height = min(height, max(560, screen.height() - 40))

    engine.setInitialProperties({"width": width, "height": height})

    engine.load(QUrl.fromLocalFile(QML_MAIN))
    if not engine.rootObjects():
        logger.error("QML 加载失败")
        return 1

    # 5. 原生窗口特效（Windows 亚克力/圆角，其他平台静默回退）
    root = engine.rootObjects()[0]
    apply_glass_effect(root)

    logger.info("液态玻璃 UI 已启动")
    return app.exec()
