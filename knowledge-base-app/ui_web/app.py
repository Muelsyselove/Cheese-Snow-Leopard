"""Web UI 装配入口 — pywebview + WebView2 内置内核（非外部浏览器）

由 main.py 调用（默认 UI 路线）：
    from ui_web.app import run_web_ui
    exit_code = run_web_ui(
        file_service=..., rag_service=..., lifecycle_service=...,
        model_config_service=..., chat_store=..., pg_repo=...,
        startup_errors=[...],
    )

说明：
- 无边框窗口 + easy_drag（标题栏/空白处拖动），窗口控制由前端经桥接调用
- 前端静态资源在 ui_web/static/，通过 file:// 加载（无外部服务器）
- 事件推送由 WebBridge._emit → window.evaluate_js 完成
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


def run_web_ui(file_service=None, rag_service=None, lifecycle_service=None,
               model_config_service=None, chat_store=None, pg_repo=None,
               startup_errors: list[str] | None = None) -> int:
    """创建并运行 Web UI，返回进程退出码"""
    try:
        import webview
    except ImportError:
        logger.error("pywebview 未安装，无法启动 Web UI。"
                     "请执行: pip install pywebview"
                     "（或使用 python main.py --ui=qml 回退 old_v2）")
        return 1

    from ui_web.bridge import WebBridge
    bridge = WebBridge(
        file_service=file_service, rag_service=rag_service,
        lifecycle_service=lifecycle_service,
        model_config_service=model_config_service, chat_store=chat_store,
        pg_repo=pg_repo, startup_errors=startup_errors,
    )

    index_path = os.path.join(STATIC_DIR, "index.html")
    window = webview.create_window(
        "知识学爆 Cheese Snow Leopard",
        index_path,
        js_api=bridge,
        width=1240, height=800,
        min_size=(960, 620),
        frameless=True,
        easy_drag=True,
        background_color="#0B0F1E",
        text_select=True,
    )
    bridge.set_window(window)

    logger.info("Web UI 启动（pywebview + WebView2 内置内核）")
    webview.start(debug=False)
    return 0
