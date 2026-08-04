"""Web UI 冒烟测试 — 真实启动 pywebview 窗口验证前端加载与桥接

用法：
    .venv/Scripts/python.exe tests/test_web_smoke.py

验证项：
1. 窗口创建 + 前端 boot 完成（App.ready）
2. i18n 字典加载 + 语言切换事件
3. 桥接方法调用：chat_get_state / files_list / knowledge_list /
   settings_get_all / i18n_get_state / app_get_startup_errors
4. 四个页面切换渲染（chat/files/knowledge/settings DOM 非空）
5. 对话事件推送链路（chat_send 无模型时错误事件 + generating 复位）
"""
from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.WARNING,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = ""):
    RESULTS.append((name, ok, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}"
          + (f"  — {detail}" if detail else ""))


def main() -> int:
    import webview
    from ui_web.bridge import WebBridge
    from services.chat_store import ChatStore

    tmp = tempfile.mkdtemp(prefix="web_smoke_")
    chat_store = ChatStore(db_path=os.path.join(tmp, "chat.db"))
    bridge = WebBridge(chat_store=chat_store, startup_errors=["测试启动警告"])

    index = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "ui_web", "static", "index.html")
    window = webview.create_window(
        "smoke", index, js_api=bridge,
        width=1100, height=720, frameless=True, easy_drag=True,
        background_color="#0B0F1E",
    )
    bridge.set_window(window)

    def js(expr: str):
        try:
            return window.evaluate_js(expr)
        except Exception as e:
            return f"__JS_ERROR__: {e}"

    def run_checks():
        try:
            # 等待 boot 完成（注意：const App 不挂载 window，须用 typeof 检测）
            ready = False
            for _ in range(60):
                if js("typeof App !== 'undefined' && App.ready === true") is True:
                    ready = True
                    break
                time.sleep(0.5)
            check("前端 boot 完成 (App.ready)", ready,
                  "" if ready else "trace=" + str(js(
                      "(window.__bootTrace||[]).join('>')")))

            # 1. i18n
            check("i18n 字典加载",
                  js("Object.keys(App.dicts).length >= 2 && "
                     "!!App.dicts['zh_CN']['app.title']") is True)
            lang = js("App.lang")
            check("默认语言 zh_CN", lang == "zh_CN", str(lang))

            # 2. 桥接方法
            st = js("window.pywebview ? 'api-ok' : 'no-api'")
            check("pywebview api 注入", st == "api-ok", str(st))

            state = bridge.chat_get_state()
            check("chat_get_state 结构",
                  isinstance(state, dict) and "conversations" in state
                  and "models" in state)
            check("files_list 返回列表",
                  isinstance(bridge.files_list(), list))
            check("knowledge_list 返回列表",
                  isinstance(bridge.knowledge_list(), list))
            s_all = bridge.settings_get_all()
            check("settings_get_all 结构",
                  isinstance(s_all, dict)
                  and "providers" in s_all and "compute" in s_all
                  and "credentials" in s_all and "scheme" in s_all)
            i18n_st = bridge.i18n_get_state()
            check("i18n_get_state 结构",
                  "dicts" in i18n_st and "languages" in i18n_st)
            check("app_get_startup_errors",
                  bridge.app_get_startup_errors() == ["测试启动警告"])

            # 3. 启动警告对话框已弹出
            check("启动警告对话框",
                  js("!!document.querySelector('.modal')") is True)
            js("document.querySelector('.modal-backdrop')?.remove()")

            # 4. 页面切换渲染
            for page, sel in [
                ("chat", "#page-chat .chat-sidebar"),
                ("files", "#page-files .page-panel"),
                ("knowledge", "#page-knowledge .page-body"),
                ("settings", "#page-settings .settings-grid"),
            ]:
                ok = js(f"switchPage('{page}'); "
                        f"!!document.querySelector('{sel}')") is True
                check(f"页面渲染: {page}", ok)
            js("switchPage('chat')")

            # 设置页区块数量
            n_sec = js("document.querySelectorAll('#page-settings .settings-grid > .panel').length")
            check("设置页 9 个区块", n_sec == 9, f"实际 {n_sec}")

            # 5. 对话事件链路（无模型无 RAG → 错误事件 + 复位）
            conv_id = bridge.chat_send(-1, "你好", True)
            check("chat_send 创建会话", conv_id > 0, f"conv_id={conv_id}")
            time.sleep(1.0)
            check("generating 已复位", bridge._generating is False)
            check("错误气泡上屏",
                  js("document.querySelectorAll('#chat-scroll .msg-row').length >= 2")
                  is True,
                  str(js("document.querySelectorAll('#chat-scroll .msg-row').length")))
            msgs = chat_store.list_messages(conv_id)
            check("用户消息已持久化",
                  len(msgs) == 1 and msgs[0].role == "user")

            # 6. 事件推送（语言切换 → 前端刷新）
            bridge.i18n_set_language("en_US")
            time.sleep(0.6)
            check("语言切换 en_US 生效", js("App.lang") == "en_US")
            check("英文文案应用",
                  js("document.querySelector('[data-page=\"chat\"]').textContent")
                  .find("Chat") != -1 if isinstance(
                      js("document.querySelector('[data-page=\"chat\"]').textContent"), str)
                  else False)
            bridge.i18n_set_language("zh_CN")
            time.sleep(0.6)
            check("语言切回 zh_CN", js("App.lang") == "zh_CN")

            # 7. JS 运行时错误收集
            err = js("window.__lastError || null")
            check("无 window.onerror 错误", err in (None, "null"), str(err))
        except Exception as e:
            check("冒烟测试异常终止", False, str(e))
        finally:
            time.sleep(0.3)
            window.destroy()

    # JS 错误/未处理 rejection 钩子注入在 boot 前
    def inject_hook():
        for _ in range(40):
            try:
                window.evaluate_js(
                    "window.__lastError = null; "
                    "window.addEventListener('error', "
                    "e => window.__lastError = 'err:' + String(e.message)); "
                    "window.addEventListener('unhandledrejection', "
                    "e => window.__lastError = 'rej:' + String(e.reason));");
                return
            except Exception:
                time.sleep(0.25)

    def worker():
        inject_hook()
        run_checks()

    threading.Thread(target=worker, daemon=True).start()
    # 兜底：120 秒强制退出
    killer = threading.Timer(120, lambda: os._exit(2))
    killer.daemon = True
    killer.start()

    webview.start(debug=False)
    killer.cancel()

    failed = [r for r in RESULTS if not r[1]]
    print(f"\n===== 结果: {len(RESULTS) - len(failed)}/{len(RESULTS)} 通过 =====")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
