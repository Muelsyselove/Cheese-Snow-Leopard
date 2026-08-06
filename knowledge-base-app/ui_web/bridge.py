"""WebBridge — pywebview js_api 根对象

将后端服务（文件/对话/知识库/设置）暴露给 Web 前端。

通信模型：
- JS → Python：window.pywebview.api.<method>(...)，返回 Promise（同步结果）
- Python → JS：_emit(channel, event, payload) → window.evaluate_js 推送事件，
  前端 window.__bridgeEvent(channel, event, payload) 统一分发

事件通道：
- app:      toast({msg,isError}) / status(msg) / languageChanged(lang)
- chat:     conversationsChanged / userMessageAppended / assistantMessageStarted /
            reasoningChunk / answerChunk / stepsUpdated / referencesAppended /
            streamFinished / assistantError / titleUpdated / generatingChanged
- files:    documentsChanged / importProgress / importRunning / importDone
- knowledge: categoriesChanged / rebuildProgress / rebuilding / rebuildFinished
- settings: testConnectionResult / depLog / depFinished / depRunning /
            bootstrapLog / bootstrapFinished / bootstrapRunning /
            migrateFinished / migrateRunning / depsChanged / credentialsChanged

说明：
- 长任务（对话流式/导入/重建/部署/依赖/迁移/测试）全部在 daemon 线程执行，
  通过事件推送进度，不阻塞 pywebview js_api 调用线程。
- 复用 Qt Worker（RebuildWorker / InstallWorker）：信号连接普通闭包为直连，
  在工作线程内同步回调，无需 QApplication / Qt 事件循环。
"""
from __future__ import annotations

import json
import logging
import os
import threading

from PySide6.QtCore import Qt

logger = logging.getLogger(__name__)

I18N_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "static", "i18n")
LANGUAGES = {"zh_CN": "简体中文", "en_US": "English"}
DEFAULT_LANGUAGE = "zh_CN"

# 导入进度消息 → DB parse_status 映射（用于实时刷新文件状态徽章）
# 与 services/file_service.py 中 import_document 的 _report 文案保持一致。
_IMPORT_STAGE_MAP = {
    "上传文件": "parsing",
    "解析文档": "parsing",
    "AI 分类": "classifying",
    "向量化": "embedding",
    "写入存储": "storing",
    "写入向量库": "storing",
    "完成": "completed",
}


# ============================================================
# 多语言（纯 Python 版，词典与 old_v2 同源 JSON）
# ============================================================
class I18n:
    def __init__(self, config_path: str = "config.yaml"):
        self._config_path = config_path
        self._dicts: dict[str, dict] = {}
        for code in LANGUAGES:
            path = os.path.join(I18N_DIR, f"{code}.json")
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self._dicts[code] = json.load(f)
            except Exception as e:
                logger.error(f"加载语言包失败 {path}: {e}")
                self._dicts[code] = {}
        self._language = self._load_saved_language()
        if self._language not in LANGUAGES:
            self._language = DEFAULT_LANGUAGE

    def _load_saved_language(self) -> str:
        try:
            import yaml
            with open(self._config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            return (cfg.get("ui") or {}).get("language", DEFAULT_LANGUAGE)
        except Exception:
            return DEFAULT_LANGUAGE

    @property
    def language(self) -> str:
        return self._language

    @property
    def dicts(self) -> dict:
        return self._dicts

    def set_language(self, code: str):
        if code not in LANGUAGES or code == self._language:
            return
        self._language = code
        try:
            import yaml
            try:
                with open(self._config_path, "r", encoding="utf-8") as f:
                    cfg = yaml.safe_load(f) or {}
            except FileNotFoundError:
                cfg = {}
            cfg.setdefault("ui", {})["language"] = code
            with open(self._config_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)
        except Exception as e:
            logger.error(f"保存语言设置失败: {e}")

    def tr(self, key: str, **params) -> str:
        text = self._dicts.get(self._language, {}).get(key)
        if text is None:
            text = self._dicts.get(DEFAULT_LANGUAGE, {}).get(key, key)
        if params:
            try:
                for k, v in params.items():
                    text = text.replace("{" + str(k) + "}", str(v))
            except Exception:
                pass
        return text


class _EventLogHandler(logging.Handler):
    """将 logging 记录转发为 settings 通道日志事件（一键部署用）"""

    def __init__(self, emit):
        super().__init__()
        self._emit = emit

    def emit(self, record):  # noqa: A003 - logging.Handler API
        try:
            self._emit("settings", "bootstrapLog", self.format(record))
        except Exception:
            pass


# ============================================================
# WebBridge
# ============================================================
class WebBridge:
    """暴露给 JS 的 js_api 根对象（所有 public 方法可从 JS 调用）"""

    def __init__(self, file_service=None, rag_service=None,
                 lifecycle_service=None, model_config_service=None,
                 chat_store=None, pg_repo=None,
                 config_path: str = "config.yaml",
                 startup_errors: list[str] | None = None):
        self.file_service = file_service
        self.rag_service = rag_service
        self.lifecycle_service = lifecycle_service
        self.model_config_service = model_config_service
        self.chat_store = chat_store
        self.pg_repo = pg_repo
        self._config_path = config_path
        self._startup_errors = list(startup_errors or [])

        self._i18n = I18n(config_path)
        self._window = None
        self._js_ready = threading.Event()

        # 对话状态（镜像 old_v2 ChatBridge）
        self._current_conv_id: int | None = None
        self._history: list[dict] = []
        self._current_model: tuple[str, str, str] | None = None
        self._generating = False
        self._interrupted = False
        self._steps: list[dict] = []
        self._reasoning_text = ""
        self._last_refs: list[dict] = []
        self._gen_lock = threading.Lock()

        # 后台任务运行标记
        self._import_running = False
        self._rebuilding = False
        self._dep_running = False
        self._bootstrap_running = False
        self._migrate_running = False

        self._select_default_model()

        # 分类审批：AI 提议新分类时阻塞等待用户决定
        self._approvals: dict[str, dict] = {}
        self._approvals_lock = threading.Lock()
        if self.file_service is not None and \
                getattr(self.file_service, "classify", None) is not None:
            self.file_service.classify.approval_hook = \
                self._category_approval_hook

    # ---------------------------------------------------------- 基础
    def set_window(self, window):
        self._window = window

    def js_ready(self):
        """前端 pywebviewready 后调用，标记事件通道可用"""
        self._js_ready.set()
        return True

    def _emit(self, channel: str, event: str, payload=None):
        if self._window is None:
            return
        try:
            js = "window.__bridgeEvent(%s,%s,%s)" % (
                json.dumps(channel),
                json.dumps(event),
                json.dumps(payload, ensure_ascii=False),
            )
            self._window.evaluate_js(js)
        except Exception as e:
            logger.debug(f"事件推送失败 {channel}.{event}: {e}")

    def _tr(self, key: str, **params) -> str:
        return self._i18n.tr(key, **params)

    def _toast(self, msg: str, is_error: bool = False):
        self._emit("app", "toast", {"msg": msg, "isError": bool(is_error)})

    def _status(self, msg: str):
        self._emit("app", "status", msg)

    # ============================================================ 窗口控制
    def window_minimize(self):
        if self._window is not None:
            self._window.minimize()

    def window_toggle_maximize(self):
        if self._window is None:
            return
        try:
            if getattr(self, "_win_maximized", False):
                self._window.restore()
            else:
                self._window.maximize()
            self._win_maximized = not getattr(self, "_win_maximized", False)
        except Exception as e:
            logger.debug(f"最大化切换失败: {e}")

    def window_close(self):
        # pywebview 的 Window 对象没有 close()，关闭入口是 destroy()
        if self._window is not None:
            self._window.destroy()

    def window_move(self, dx: int, dy: int) -> dict:
        """无边框窗口拖动（前端标题栏 mousedown/mousemove 调用）。

        :param dx/dy: 相对上一次事件的自增屏幕像素位移（物理像素）。
            前端每次 mousemove 发送“本次 vs 上次”的增量，而非自按下累计值，
            避免累加时重复计入已发生位移。
        """
        form = getattr(self._window, "native", None)
        if form is None:
            return {}
        try:
            scale = getattr(form, "_scale", None) or 1.0
            new_x = (form.Location.X + int(dx or 0)) / scale   # 逻辑像素
            new_y = (form.Location.Y + int(dy or 0)) / scale
            self._window.move(new_x, new_y)
            return {"x": int(round(new_x)), "y": int(round(new_y))}
        except Exception as e:
            logger.debug(f"窗口移动失败: {e}")
            return {}

    def window_resize_drag(self, direction: str, dx: int, dy: int) -> dict:
        """无边框窗口边缘/角落拖动缩放（前端 .rs-handle mousedown/mousemove 调用）。

        :param direction: 'n'/'s'/'e'/'w'/'ne'/'nw'/'se'/'sw'
        :param dx/dy: 相对上一次事件的自增屏幕像素位移（物理像素），
            配合下方按当前宽高计算，避免位移重复累加。
        :return: 缩放后的逻辑宽高。
        """
        form = getattr(self._window, "native", None)
        if form is None:
            return {}
        try:
            scale = getattr(form, "_scale", None) or 1.0
            w = form.Width / scale                      # 逻辑像素
            h = form.Height / scale
            loc_x_p = form.Location.X                   # 物理像素
            loc_y_p = form.Location.Y
            dx = int(dx or 0)
            dy = int(dy or 0)
            d = (direction or "").lower()

            new_w = w
            new_h = h
            move_x_p = loc_x_p
            move_y_p = loc_y_p
            if "e" in d:
                new_w = w + dx / scale
            if "w" in d:
                new_w = w - dx / scale
                move_x_p = loc_x_p + dx
            if "s" in d:
                new_h = h + dy / scale
            if "n" in d:
                new_h = h - dy / scale
                move_y_p = loc_y_p + dy

            # 最小尺寸钳制（物理像素）
            min_w_p = form.MinimumSize.Width if hasattr(form, "MinimumSize") else 0
            min_h_p = form.MinimumSize.Height if hasattr(form, "MinimumSize") else 0
            new_w_p = max(int(round(new_w * scale)), min_w_p)
            new_h_p = max(int(round(new_h * scale)), min_h_p)
            # 西/北边被最小尺寸截断时，位置需回退以保持尺寸正确
            if "w" in d:
                move_x_p = loc_x_p + dx - (int(round(new_w * scale)) - new_w_p)
            if "n" in d:
                move_y_p = loc_y_p + dy - (int(round(new_h * scale)) - new_h_p)

            if move_x_p != loc_x_p or move_y_p != loc_y_p:
                self._window.move(move_x_p / scale, move_y_p / scale)
            # 固定左上角（FixPoint.NORTH|WEST 默认值）缩放
            self._window.resize(new_w_p / scale, new_h_p / scale)
            return {"width": int(round(new_w)), "height": int(round(new_h))}
        except Exception as e:
            logger.debug(f"窗口缩放失败: {e}")
            return {}

    def window_get_bounds(self) -> dict:
        """返回窗口当前物理像素边界（绝对定位拖动/缩放用）"""
        form = getattr(self._window, "native", None)
        if form is None:
            return {}
        try:
            return {"x": int(form.Location.X), "y": int(form.Location.Y),
                    "width": int(form.Width), "height": int(form.Height)}
        except Exception as e:
            logger.debug(f"读取窗口边界失败: {e}")
            return {}

    def window_move_abs(self, x: int, y: int):
        """无边框窗口绝对定位（物理像素）——前端按光标位置平滑拖动"""
        form = getattr(self._window, "native", None)
        if form is None:
            return
        try:
            scale = getattr(form, "_scale", None) or 1.0
            self._window.move(int(x) / scale, int(y) / scale)
        except Exception as e:
            logger.debug(f"窗口绝对移动失败: {e}")

    def window_resize_abs(self, direction: str, start_x: int, start_y: int,
                          start_w: int, start_h: int, dx: int, dy: int) -> dict:
        """无边框窗口边缘/角落缩放（绝对定位，物理像素）。

        以按下时的起始边界 + 自按下累计位移计算目标矩形，
        避免增量累加造成的漂移与滞后，使缩放跟手。
        """
        form = getattr(self._window, "native", None)
        if form is None:
            return {}
        try:
            d = (direction or "").lower()
            dx = int(dx or 0)
            dy = int(dy or 0)
            scale = getattr(form, "_scale", None) or 1.0
            new_x, new_y = int(start_x), int(start_y)
            new_w, new_h = int(start_w), int(start_h)
            if "e" in d:
                new_w = start_w + dx
            if "s" in d:
                new_h = start_h + dy
            if "w" in d:
                new_w = start_w - dx
                new_x = start_x + dx
            if "n" in d:
                new_h = start_h - dy
                new_y = start_y + dy
            # 最小尺寸钳制（西/北边被截断时位置回退）
            min_w = form.MinimumSize.Width if hasattr(
                form, "MinimumSize") else 0
            min_h = form.MinimumSize.Height if hasattr(
                form, "MinimumSize") else 0
            if new_w < min_w:
                if "w" in d:
                    new_x = start_x + (start_w - min_w)
                new_w = min_w
            if new_h < min_h:
                if "n" in d:
                    new_y = start_y + (start_h - min_h)
                new_h = min_h
            self._window.move(new_x / scale, new_y / scale)
            self._window.resize(new_w / scale, new_h / scale)
            return {"width": int(round(new_w / scale)),
                    "height": int(round(new_h / scale))}
        except Exception as e:
            logger.debug(f"窗口绝对缩放失败: {e}")
            return {}

    def open_external(self, url: str):
        """在系统默认浏览器打开外部链接（仅用于申请 Key / 文档等显式外链）"""
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception as e:
            logger.warning(f"打开外链失败 {url}: {e}")

    # ============================================================ 应用信息
    def app_get_startup_errors(self) -> list[str]:
        return list(self._startup_errors)

    # ============================================================ 多语言
    def i18n_get_state(self) -> dict:
        return {
            "language": self._i18n.language,
            "languages": [{"code": c, "name": n}
                          for c, n in LANGUAGES.items()],
            "dicts": self._i18n.dicts,
        }

    def i18n_set_language(self, code: str):
        self._i18n.set_language(code)
        self._emit("app", "languageChanged", self._i18n.language)

    # ============================================================ 对话
    def _models(self) -> list[dict]:
        if self.model_config_service is None:
            return []
        return [
            {"providerKey": pk, "providerName": pn,
             "modelName": mn, "displayName": md,
             "label": f"[{pn}] {md}"}
            for pk, pn, mn, md in self.model_config_service.list_enabled_models()
        ]

    def _select_default_model(self):
        models = self._models()
        if not models:
            self._current_model = None
            return
        default = None
        if self.model_config_service is not None:
            default = self.model_config_service.get_default_models().get("chat")
        if default:
            for m in models:
                if m["providerKey"] == default[0] and \
                        m["modelName"] == default[1]:
                    self._current_model = (m["providerKey"], m["modelName"],
                                           m["displayName"])
                    return
        first = models[0]
        self._current_model = (first["providerKey"], first["modelName"],
                               first["displayName"])

    def _conversations(self) -> list[dict]:
        if self.chat_store is None:
            return []
        return [
            {"convId": c.id,
             "title": c.title or self._tr("chat.newConversationTitle"),
             "autoName": bool(c.auto_name),
             "model": c.model or ""}
            for c in self.chat_store.list_conversations()
        ]

    def chat_get_state(self) -> dict:
        cur = self._current_model
        return {
            "conversations": self._conversations(),
            "currentConvId": self._current_conv_id or -1,
            "models": self._models(),
            "currentModel": (
                {"providerKey": cur[0], "modelName": cur[1],
                 "displayName": cur[2]} if cur else None),
            "generating": self._generating,
            "hasRag": self.rag_service is not None,
            "storeReady": self.chat_store is not None,
        }

    def chat_reload_models(self):
        """设置页保存模型配置后刷新"""
        if self.model_config_service is not None:
            self.model_config_service.load()
        self._select_default_model()
        return self.chat_get_state()

    def chat_select_model(self, provider_key: str, model_name: str,
                          display_name: str):
        self._current_model = (provider_key, model_name, display_name)
        if self._current_conv_id and self.chat_store:
            self.chat_store.set_conversation_model(
                self._current_conv_id, model_name)
        return True

    def chat_new_conversation(self) -> int:
        if self.chat_store is None:
            self._toast(self._tr("chat.chatStoreNotReady"))
            return -1
        conv = self.chat_store.create_conversation(
            title=self._tr("chat.newConversationTitle"))
        self._current_conv_id = conv.id
        self._history = []
        self._emit("chat", "conversationsChanged", self._conversations())
        return conv.id

    def chat_select_conversation(self, conv_id: int) -> dict:
        if self.chat_store is None:
            return {"messages": []}
        conv = self.chat_store.get_conversation(conv_id)
        if conv is None:
            return {"messages": []}
        self._current_conv_id = conv_id
        self._history = []
        messages = []
        for msg in self.chat_store.list_messages(conv_id):
            self._history.append({"role": msg.role, "content": msg.content})
            if msg.role in ("user", "assistant"):
                messages.append({"role": msg.role, "content": msg.content,
                                 "meta": msg.meta})
        # 恢复该对话所用模型
        if conv.model:
            for m in self._models():
                if m["modelName"] == conv.model:
                    self._current_model = (m["providerKey"], m["modelName"],
                                           m["displayName"])
                    break
        return {"messages": messages, "title": conv.title,
                "autoName": bool(conv.auto_name)}

    def chat_delete_conversation(self, conv_id: int):
        if self.chat_store is None:
            return
        self.chat_store.delete_conversation(conv_id)
        if self._current_conv_id == conv_id:
            self._current_conv_id = None
            self._history = []
        self._emit("chat", "conversationsChanged", self._conversations())

    def chat_rename_conversation(self, conv_id: int, title: str):
        if self.chat_store is None or not (title or "").strip():
            return
        self.chat_store.rename_conversation(conv_id, title.strip())
        self._emit("chat", "conversationsChanged", self._conversations())

    def chat_set_auto_name(self, conv_id: int, enabled: bool):
        if self.chat_store is not None:
            self.chat_store.set_auto_name(conv_id, bool(enabled))
            self._emit("chat", "conversationsChanged", self._conversations())

    def chat_get_conversation_info(self, conv_id: int) -> dict:
        if self.chat_store is None:
            return {}
        conv = self.chat_store.get_conversation(conv_id)
        if conv is None:
            return {}
        return {"convId": conv.id, "title": conv.title,
                "autoName": bool(conv.auto_name)}

    # ---------------------------------------------------------- 发送 / 中断
    def chat_send(self, conv_id: int, text: str, thinking: bool,
                  thinking_strength: str = "auto") -> int:
        """发送消息（生成在后台线程进行，流式事件推送）。返回会话 ID。"""
        question = (text or "").strip()
        if not question:
            return conv_id or -1
        with self._gen_lock:
            if self._generating:
                return conv_id or -1
            self._generating = True

        if (conv_id or 0) <= 0 and self.chat_store is not None:
            conv = self.chat_store.create_conversation(
                title=self._tr("chat.newConversationTitle"))
            conv_id = conv.id
            self._emit("chat", "conversationsChanged", self._conversations())
        self._current_conv_id = conv_id if (conv_id or 0) > 0 else None

        llm = self._get_llm_client()
        self._emit("chat", "userMessageAppended", question)
        self._history.append({"role": "user", "content": question})
        if self.chat_store and self._current_conv_id:
            self.chat_store.add_message(self._current_conv_id, "user", question)

        if llm is None and self.rag_service is None:
            self._emit("chat", "assistantError",
                       self._tr("chat.noModelNoRag"))
            with self._gen_lock:
                self._generating = False
            self._emit("chat", "generatingChanged", False)
            return self._current_conv_id or -1

        self._interrupted = False
        self._steps = []
        self._reasoning_text = ""
        self._last_refs = []
        self._emit("chat", "assistantMessageStarted", None)
        self._emit("chat", "generatingChanged", True)
        history = list(self._history)
        threading.Thread(
            target=self._chat_run,
            args=(question, history, llm, bool(thinking),
                  (thinking_strength or "auto")),
            daemon=True,
        ).start()
        return self._current_conv_id or -1

    def chat_stop(self):
        self._interrupted = True

    def _get_llm_client(self):
        if self._current_model is None or self.model_config_service is None:
            return None
        try:
            return self.model_config_service.create_llm_client(
                self._current_model[0], self._current_model[1])
        except Exception as e:
            logger.error(f"创建 LLM 客户端失败: {e}")
            return None

    # ---- 流式执行（后台线程），步骤状态机镜像 old_v2 ChatBridge ----
    def _chat_run(self, question: str, history: list[dict], llm,
                  thinking: bool, thinking_strength: str = "auto"):
        answer = ""
        try:
            should_stop = lambda: self._interrupted  # noqa: E731
            if self.rag_service is not None:
                stream = self.rag_service.stream_query(
                    question, history, llm=llm, thinking=thinking,
                    thinking_strength=thinking_strength,
                    should_stop=should_stop)
            else:
                stream = llm.stream_chat(
                    history, thinking=thinking,
                    thinking_strength=thinking_strength,
                    should_stop=should_stop)
            for kind, text in stream:
                if self._interrupted:
                    break
                if kind == "reasoning":
                    self._on_reasoning(text)
                elif kind == "content":
                    answer += text
                    self._on_token(text)
                elif kind == "step":
                    self._on_step_event(text)

            # 引用来源（仅 RAG 路径且未中断）
            if not self._interrupted and self.rag_service is not None:
                try:
                    retrieved = set(getattr(
                        self.rag_service, "last_retrieved_chunks", set()))
                    if retrieved:
                        from services.trace_service import (
                            trace_references, trace_references_fallback)
                        refs = trace_references(answer, retrieved)
                        if not refs:
                            refs = trace_references_fallback(answer, retrieved)
                        if refs:
                            self._last_refs = refs
                            self._emit("chat", "referencesAppended", refs)
                except Exception as e:
                    logger.debug(f"引用溯源失败（非致命）: {e}")
        except Exception as e:
            logger.error(f"对话生成失败: {e}", exc_info=True)
            self._emit("chat", "assistantError",
                       self._tr("chat.requestFailed", msg=e))
            answer = ""
        finally:
            self._finalize_stream(answer)

    def _on_reasoning(self, text: str):
        if not self._steps or self._steps[-1]["kind"] != "thinking" \
                or self._steps[-1]["status"] != "running":
            self._steps.append({"kind": "thinking", "status": "running",
                                "detail": ""})
            self._emit("chat", "stepsUpdated", list(self._steps))
        self._reasoning_text += text
        self._emit("chat", "reasoningChunk", text)

    def _on_token(self, text: str):
        changed = False
        if self._steps and self._steps[-1]["kind"] == "thinking" \
                and self._steps[-1]["status"] == "running":
            self._steps[-1]["status"] = "done"
            changed = True
        if not any(s["kind"] == "answer" for s in self._steps):
            self._steps.append({"kind": "answer", "status": "running",
                                "detail": ""})
            changed = True
        if changed:
            self._emit("chat", "stepsUpdated", list(self._steps))
        self._emit("chat", "answerChunk", text)

    def _on_step_event(self, event: dict):
        op = event.get("op")
        kind = event.get("kind", "")
        if op == "start":
            self._close_running_step("thinking")
            self._steps.append({"kind": kind, "status": "running",
                                "detail": str(event.get("detail", ""))})
        elif op == "done":
            for s in reversed(self._steps):
                if s["kind"] == kind and s["status"] == "running":
                    s["status"] = "done"
                    s["detail"] = event.get("detail", "")
                    break
        self._emit("chat", "stepsUpdated", list(self._steps))

    def _close_running_step(self, kind: str):
        for s in reversed(self._steps):
            if s["kind"] == kind and s["status"] == "running":
                s["status"] = "done"
                return

    def _finalize_stream(self, answer: str):
        if answer and not self._interrupted:
            self._history.append({"role": "assistant", "content": answer})
            if self.chat_store and self._current_conv_id:
                meta = {
                    "steps": self._steps,
                    "reasoning": self._reasoning_text,
                    "refs": self._last_refs,
                }
                self.chat_store.add_message(
                    self._current_conv_id, "assistant", answer, meta=meta)
            self._maybe_auto_name()
        any_running = False
        for s in self._steps:
            if s["status"] == "running":
                s["status"] = "done"
                any_running = True
        if any_running:
            self._emit("chat", "stepsUpdated", list(self._steps))
        with self._gen_lock:
            self._generating = False
        self._emit("chat", "generatingChanged", False)
        self._emit("chat", "streamFinished", None)

    # ---------------------------------------------------------- 自动命名
    def _get_auto_naming_client(self):
        if self.model_config_service is None:
            return None
        try:
            rt = self.model_config_service.get_default_model_for_role(
                "auto_naming")
            if rt:
                # get_model_runtime 返回顺序为 (api_base, api_key, model_name)
                api_base, api_key, model_name = rt
                from adapters.openai_llm import OpenAILLMClient
                return OpenAILLMClient(
                    api_base=api_base, api_key=api_key, model=model_name,
                    temperature=0.3, max_tokens=4096, timeout=60)
        except Exception as e:
            logger.warning(f"使用自动命名模型失败，回退当前模型: {e}")
        return self._get_llm_client()

    def chat_re_auto_name(self, conv_id: int):
        if self.chat_store is None:
            return
        conv = self.chat_store.get_conversation(conv_id)
        if conv is None:
            return
        messages = self.chat_store.list_messages(conv_id)
        user_msg = assistant_msg = ""
        for m in messages:
            if m.role == "user" and not user_msg:
                user_msg = m.content
            elif m.role == "assistant" and not assistant_msg:
                assistant_msg = m.content
            if user_msg and assistant_msg:
                break
        if not user_msg:
            self._toast(self._tr("chat.noContentToName"))
            return
        llm = self._get_auto_naming_client()
        if llm is None:
            self._toast(self._tr("chat.configModelFirst"))
            return
        threading.Thread(target=self._title_run,
                         args=(llm, user_msg, assistant_msg, conv_id),
                         daemon=True).start()

    def _title_run(self, llm, user_msg: str, assistant_msg: str, conv_id: int):
        try:
            prompt = (
                "请为以下对话生成一个简短的中文标题（不超过12个字，不要加引号、不要句号）。"
                "只返回标题本身：\n\n"
                f"用户：{user_msg[:200]}\n"
                f"助手：{assistant_msg[:200]}"
            )
            # 自动命名一律使用非思考模式，避免推理模型耗时/报错；不支持时自动降级
            resp = llm.chat([{"role": "user", "content": prompt}],
                            thinking=False)
            title = (resp.get("content", "") or "").strip()
            title = title.strip("\"'“”‘’「」\n ")
            if not title:
                title = self._tr("chat.newConversationTitle")
            if len(title) > 20:
                title = title[:20]
            if self.chat_store:
                self.chat_store.rename_conversation(conv_id, title)
                self._emit("chat", "titleUpdated",
                           {"convId": conv_id, "title": title})
                self._emit("chat", "conversationsChanged",
                           self._conversations())
        except Exception as e:
            self._toast(self._tr("chat.autoNameFailed", msg=e))

    def _maybe_auto_name(self):
        if self._current_conv_id is None or self.chat_store is None:
            return
        conv = self.chat_store.get_conversation(self._current_conv_id)
        if conv is None or not conv.auto_name:
            return
        if conv.title and conv.title != self._tr("chat.newConversationTitle") \
                and conv.title != "新对话":
            return
        # 仅首次对话（第一条用户消息）时自动命名，之后不再自动重复触发
        user_count = sum(1 for m in self.chat_store.list_messages(
            self._current_conv_id) if m.role == "user")
        if user_count != 1:
            return
        self.chat_re_auto_name(self._current_conv_id)

    # ============================================================ 文件
    def files_list(self) -> list[dict]:
        if self.file_service is None:
            return []
        try:
            docs = self.file_service.list_documents()
        except Exception as e:
            logger.warning(f"加载已导入文档失败: {e}")
            return []
        result = []
        for d in docs:
            status = getattr(d, "parse_status", "completed") or "completed"
            result.append({
                "docId": str(getattr(d, "doc_id", None) or -1),
                "fileName": getattr(d, "file_name", str(d)),
                "status": status,
                "statusKey": f"files.status.{status}",
                "pageCount": str(getattr(d, "page_count", "") or ""),
            })
        return result

    def files_pick(self) -> list[str]:
        """原生多选文件对话框，返回所选路径"""
        if self._window is None:
            return []
        try:
            import webview
            result = self._window.create_file_dialog(
                webview.OPEN_DIALOG, allow_multiple=True,
                file_types=(
                    "Documents (*.pdf;*.docx;*.png;*.jpg;*.jpeg;*.txt;*.md;*.markdown)",
                    "All files (*.*)",
                ))
            return list(result) if result else []
        except Exception as e:
            logger.error(f"文件选择对话框失败: {e}")
            return []

    def files_import(self, paths: list[str]):
        """后台导入所选文件（进度事件推送）"""
        if self.file_service is None:
            self._toast(self._tr("files.serviceNotReady"))
            return False
        paths = [p for p in (paths or []) if p]
        if not paths or self._import_running:
            return False
        self._import_running = True
        self._emit("files", "importRunning", True)
        threading.Thread(target=self._import_run, args=(paths,),
                         daemon=True).start()
        return True

    def _import_run(self, paths: list[str]):
        results = 0
        total = len(paths)
        for i, path in enumerate(paths):
            try:
                base = int(i / total * 100) if total else 0
                next_base = int((i + 1) / total * 100) if total else 100
                span = max(next_base - base, 1)
                # 可变容器：记录当前文件已上报的阶段，阶段变化时刷新状态徽章
                last_stage = {"stage": None}

                def _cb(pct, msg, base=base, span=span, path=path,
                        last_stage=last_stage):
                    self._emit("files", "importProgress", {
                        "percent": base + int((pct / 100) * span),
                        "msg": f"{msg}: {path}",
                    })
                    stage = self._import_stage_from_msg(msg)
                    if stage and stage != last_stage["stage"]:
                        last_stage["stage"] = stage
                        self._emit("files", "documentsChanged",
                                   self.files_list())

                self._emit("files", "importProgress",
                           {"percent": base, "msg": f"正在导入: {path}"})
                self.file_service.import_document(path, progress_cb=_cb)
                results += 1
                self._emit("files", "importProgress",
                           {"percent": next_base, "msg": f"已导入: {path}"})
            except Exception as e:
                logger.error(f"导入失败 {path}: {e}", exc_info=True)
                self._toast(f"{path}: {e}", is_error=True)
                self._status(self._tr("status.failed"))
        self._import_running = False
        self._emit("files", "importRunning", False)
        self._emit("files", "importProgress", {"percent": 100, "msg": ""})
        self._emit("files", "documentsChanged", self.files_list())
        self._emit("files", "importDone", results)
        self._status(self._tr("files.imported", count=results))

    @staticmethod
    def _import_stage_from_msg(msg: str) -> str | None:
        """将导入进度消息映射为 DB parse_status，用于实时刷新状态徽章。"""
        for key, stage in _IMPORT_STAGE_MAP.items():
            if key in (msg or ""):
                return stage
        return None

    def files_delete(self, doc_id):
        # doc_id 为雪花算法 64 位整数，前端以字符串回传避免 JS 精度丢失
        if self.lifecycle_service is None:
            self._toast(self._tr("files.lifecycleNotReady"))
            return False
        try:
            self.lifecycle_service.delete_document(int(doc_id))
            # 立即触发补偿清理，不等 reconciler 30 秒轮询
            threading.Thread(target=self._compensation_run_once,
                             daemon=True).start()
            self._status(self._tr("files.deleteQueued"))
            self._emit("files", "documentsChanged", self.files_list())
            return True
        except Exception as e:
            logger.error(f"删除文档失败 doc_id={doc_id}: {e}", exc_info=True)
            self._toast(self._tr("files.deleteFailed", msg=e), is_error=True)
            return False

    def _compensation_run_once(self):
        try:
            self.lifecycle_service.compensation.run_once()
        except Exception as e:
            logger.warning(f"补偿清理执行失败: {e}")
        # 清理完成后再次刷新文件列表（delete 的实际清理由补偿执行）
        self._emit("files", "documentsChanged", self.files_list())

    def files_open_source(self, doc_id: str) -> bool:
        """从 MinIO 下载源文件到临时目录并用系统默认程序打开"""
        if self.pg_repo is None or self.file_service is None:
            self._toast(self._tr("files.openFailed", msg="service not ready"),
                        is_error=True)
            return False
        doc = self.pg_repo.get_document(int(doc_id))
        if doc is None:
            self._toast(self._tr("files.openFailed", msg="记录不存在"),
                        is_error=True)
            return False
        try:
            try:
                from utils.paths import get_tmp_dir
                tmp_dir = get_tmp_dir()
            except Exception:
                import tempfile
                tmp_dir = tempfile.gettempdir()
            local_path = os.path.join(tmp_dir, doc.file_name)
            self.file_service.minio.download(doc.file_path, local_path)
            os.startfile(local_path)  # Windows
            self._status(self._tr("files.opening"))
            return True
        except Exception as e:
            logger.error(f"打开源文件失败 doc_id={doc_id}: {e}", exc_info=True)
            self._toast(self._tr("files.openFailed", msg=e), is_error=True)
            return False

    # ---------------------------------------------------------- 分类审批
    def _category_approval_hook(self, suggested_path, content_preview,
                                doc_name):
        """ClassifyService 的 approval_hook：推送审批弹窗并阻塞等待用户决定
        （180s 超时归入未分类）。返回非空路径列表 = 使用该路径；None = 未分类。"""
        import uuid
        req_id = uuid.uuid4().hex
        entry = {"event": threading.Event(), "path": None}
        with self._approvals_lock:
            self._approvals[req_id] = entry
        self._emit("files", "categoryApproval", {
            "requestId": req_id,
            "suggestedPath": [str(p) for p in (suggested_path or [])],
            "preview": (content_preview or "")[:200],
            "docName": doc_name or "",
            "tree": self._existing_category_paths(),
        })
        entry["event"].wait(timeout=180)
        with self._approvals_lock:
            self._approvals.pop(req_id, None)
        if entry.get("allow"):
            return [str(p) for p in (suggested_path or [])]
        return entry["path"] if entry["path"] else None

    def _existing_category_paths(self) -> list[list[str]]:
        """全部现有分类的完整路径（供审批弹窗选择现有分类）"""
        if self.pg_repo is None:
            return []
        try:
            cats = self.pg_repo.list_all_categories()
        except Exception:
            return []
        by_id = {c.category_id: c for c in cats}
        paths = []
        for c in cats:
            chain, node, seen = [], c, set()
            while node is not None and node.category_id not in seen:
                seen.add(node.category_id)
                chain.append(node.name)
                node = by_id.get(node.parent_id)
            paths.append(list(reversed(chain)))
        return paths

    def files_resolve_category(self, request_id: str, action: str, path=None):
        """前端审批回调。action: allow(用建议路径) / choose(选择现有) /
        custom(自建) / other(归入未分类)"""
        with self._approvals_lock:
            entry = self._approvals.get(str(request_id))
        if entry is None:
            return False
        if action == "allow":
            entry["path"] = None  # None 表示沿用建议路径（由 hook 返回建议值）
            entry["allow"] = True
        elif action in ("choose", "custom") and path:
            entry["path"] = [str(p) for p in path if str(p).strip()]
        else:
            entry["path"] = []
        entry["event"].set()
        return True

    # ============================================================ 知识库
    def knowledge_list(self) -> list[dict]:
        if self.pg_repo is None:
            return []
        try:
            cats = self.pg_repo.list_all_categories()
        except Exception as e:
            logger.warning(f"加载分类失败: {e}")
            return []
        return [{"name": getattr(c, "name", str(c)),
                 "chunkCount": int(getattr(c, "chunk_count", 0) or 0)}
                for c in cats]

    def knowledge_rebuild(self):
        if self.lifecycle_service is None:
            self._toast(self._tr("knowledge.lifecycleNotReady"))
            return False
        if self._rebuilding:
            return False
        try:
            worker = self.lifecycle_service.rebuild_vector_store()
        except Exception as e:
            self._toast(self._tr("knowledge.rebuildStartFailed", msg=e),
                        is_error=True)
            return False

        # 信号 → 事件（直连闭包，在 worker 线程同步回调）
        # 注意：worker 由 threading.Thread 调用 run()（非 QThread.start()），
        # 无 Qt 事件循环，必须显式 Qt.DirectConnection，否则 AutoConnection
        # 会走 queued 投递而永不执行，导致 UI 卡在"正在重建"。
        worker.progress.connect(
            lambda pct, msg: (self._emit("knowledge", "rebuildProgress",
                                         {"percent": pct, "msg": msg}),
                              self._status(f"{msg} ({pct}%)")),
            Qt.DirectConnection)
        worker.finished.connect(self._on_rebuild_done, Qt.DirectConnection)
        worker.error.connect(
            lambda msg: self._toast(msg, is_error=True),
            Qt.DirectConnection)
        self._rebuilding = True
        self._emit("knowledge", "rebuilding", True)
        self._status(self._tr("knowledge.rebuildStarted"))
        # 直接调用 run()（不开 QThread，无需 Qt 事件循环）
        threading.Thread(target=worker.run, daemon=True).start()
        return True

    def _on_rebuild_done(self, success: bool):
        self._rebuilding = False
        self._emit("knowledge", "rebuilding", False)
        self._emit("knowledge", "rebuildFinished", bool(success))
        self._emit("knowledge", "categoriesChanged", self.knowledge_list())
        self._status(self._tr("knowledge.rebuildDone") if success
                     else self._tr("knowledge.rebuildFailed"))

    # ---------------------------------------------------------- 知识库仪表盘
    def knowledge_dashboard(self) -> dict:
        """返回 {total: int, tree: [...]}。tree 为嵌套结构：
        [{id: str, name: str, count: int(含后代), children: [...]}]
        total = chunk_category 关联总数（含多分类重复）"""
        if self.pg_repo is None:
            return {"total": 0, "tree": []}
        try:
            cats = self.pg_repo.list_all_categories()
        except Exception as e:
            logger.warning(f"加载分类失败: {e}")
            return {"total": 0, "tree": []}
        try:
            total = int(self.pg_repo.count_chunk_category_links())
        except Exception:
            total = 0

        nodes = {}
        children_map: dict[int, list] = {}
        for c in cats:
            cid = c.category_id
            nodes[cid] = {"id": str(cid), "name": c.name,
                          "count": int(getattr(c, "chunk_count", 0) or 0),
                          "children": []}
            children_map.setdefault(c.parent_id, []).append(cid)

        def _sum(cid: int) -> int:
            node = nodes[cid]
            for child_id in children_map.get(cid, []):
                node["count"] += _sum(child_id)
                node["children"].append(nodes[child_id])
            return node["count"]

        tree = []
        root_ids = [c.category_id for c in cats
                    if not c.parent_id or c.parent_id not in nodes]
        for cid in root_ids:
            _sum(cid)
            tree.append(nodes[cid])
        return {"total": total, "tree": tree}

    def knowledge_random_chunks(self, category_id: str = "",
                                limit: int = 12) -> list[dict]:
        """随机知识卡片。category_id 为空串/"0" 时全库随机；否则含全部后代分类。
        返回 [{docName, content, page}]，content 截断到 300 字。"""
        if self.pg_repo is None:
            return []
        try:
            cid_str = str(category_id or "").strip()
            if cid_str and cid_str != "0":
                cats = self.pg_repo.list_all_categories()
                children_map: dict[int, list] = {}
                for c in cats:
                    children_map.setdefault(c.parent_id, []).append(
                        c.category_id)
                root = int(cid_str)
                ids, stack = [], [root]
                while stack:
                    cur = stack.pop()
                    ids.append(cur)
                    stack.extend(children_map.get(cur, []))
                chunks = self.pg_repo.list_random_chunks_by_category(
                    ids, int(limit))
            else:
                chunks = self.pg_repo.list_random_chunks(int(limit))
        except Exception as e:
            logger.warning(f"随机知识卡片查询失败: {e}")
            return []
        return [{"docName": getattr(ch, "doc_name", "") or "",
                 "content": (getattr(ch, "content", "") or "")[:300],
                 "page": getattr(ch, "page_number", None)}
                for ch in chunks]

    def knowledge_reset_all(self) -> bool:
        """全量清空知识库并重建预置分类"""
        if self.lifecycle_service is None:
            self._toast(self._tr("knowledge.lifecycleNotReady"))
            return False
        try:
            self.lifecycle_service.reset_all()
            if self.file_service is not None and \
                    getattr(self.file_service, "classify", None) is not None:
                self.file_service.classify.ensure_preset_taxonomy()
            self._toast(self._tr("knowledge.resetDone"))
            self._emit("knowledge", "categoriesChanged", [])
            self._emit("files", "documentsChanged", self.files_list())
            return True
        except Exception as e:
            logger.error(f"知识库全量重置失败: {e}", exc_info=True)
            self._toast(self._tr("knowledge.resetFailed", msg=e),
                        is_error=True)
            return False

    # ============================================================ 设置
    def _load_config(self) -> dict:
        import yaml
        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.error(f"加载 config.yaml 失败: {e}")
            return {}

    def _save_config(self, cfg: dict):
        import yaml
        with open(self._config_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)

    def _providers(self) -> list[dict]:
        from services.model_config_service import ModelConfigService  # noqa: F401
        result = []
        svc = self.model_config_service
        if svc is None:
            return result
        for preset, pc in svc.list_providers():
            model_display = {m.model_name: m.display_name
                             for m in preset.models}
            result.append({
                "key": preset.key,
                "displayName": preset.display_name,
                "apiBase": preset.api_base,
                "docUrl": preset.doc_url,
                "keyApplyUrl": preset.key_apply_url,
                "configured": pc.configured,
                "hasApiKey": bool(pc.api_key),
                "models": [
                    {"modelName": mc.model_name,
                     "displayName": model_display.get(mc.model_name,
                                                      mc.model_name),
                     "enabled": mc.enabled}
                    for mc in pc.models
                ],
            })
        return result

    def _default_roles(self) -> list[dict]:
        from services.model_config_service import DEFAULT_ROLES
        defaults = (self.model_config_service.get_default_models()
                    if self.model_config_service else {})
        result = []
        for role in DEFAULT_ROLES:
            ref = defaults.get(role)
            result.append({
                "role": role,
                "roleKey": f"settings.role.{role}",
                "providerKey": ref[0] if ref else "",
                "modelName": ref[1] if ref else "",
            })
        return result

    def settings_get_all(self) -> dict:
        """设置页一次性初始化数据"""
        from services.dependency_service import DependencyService
        from services.credential_service import CredentialService
        cfg = self._load_config()
        dep = DependencyService()
        cred = CredentialService()
        cred_status = cred.get_status()
        # 计算设备（GPU 检测结果缓存：运行期间硬件不变，避免重复探测阻塞）
        compute_options = []
        compute_device = "auto"
        compute_active = ""
        try:
            if getattr(self, "_gpu_cache", None) is None:
                from services.gpu_service import detect_gpus
                self._gpu_cache = detect_gpus()
            from services.gpu_service import strongest_gpu
            gpus = self._gpu_cache
            best = strongest_gpu(gpus)
            if best is not None:
                compute_options.append({
                    "value": "auto",
                    "label": self._tr("settings.compute.autoWith",
                                      name=best.name)})
            else:
                compute_options.append({
                    "value": "auto",
                    "label": self._tr("settings.compute.autoNoGpu")})
            for g in gpus:
                compute_options.append({
                    "value": f"cuda:{g.index}",
                    "label": f"GPU {g.index} · {g.name} · "
                             f"{g.vram_mb // 1024} GB"})
            compute_options.append({
                "value": "cpu",
                "label": self._tr("settings.compute.cpuOnly")})
            compute_device = (cfg.get("compute") or {}).get("device", "auto")
            vis = os.environ.get("CUDA_VISIBLE_DEVICES")
            if vis == "":
                compute_active = "CPU"
            elif vis:
                compute_active = f"GPU {vis}"
            else:
                compute_active = self._tr("settings.compute.activeDefault")
        except Exception as e:
            logger.warning(f"GPU 检测失败: {e}")
        # 数据根目录
        try:
            from utils.paths import get_data_root
            data_root = get_data_root()
        except Exception:
            from utils.paths import DEFAULT_DATA_ROOT
            data_root = DEFAULT_DATA_ROOT
        return {
            "language": self._i18n.language,
            "languages": [{"code": c, "name": n}
                          for c, n in LANGUAGES.items()],
            "providers": self._providers(),
            "defaultRoles": self._default_roles(),
            "enabledModels": self._models(),
            "credentials": [
                {"key": item.key, "name": item.name,
                 "description": item.description,
                 "placeholder": item.placeholder or item.name,
                 "isSet": cred_status.get(item.key, False)}
                for item in cred.list_items()
            ],
            "coreDeps": [{"name": pkg, "installed": ok}
                         for pkg, ok in dep.get_core_status().items()],
            "optionalComponents": [
                {"key": c.key, "name": c.name, "description": c.description,
                 "packages": list(c.packages),
                 "installed": dep.get_status().get(c.key, False)}
                for c in dep.list_components()
            ],
            "scheme": {
                "vlm": (cfg.get("vlm") or {}).get("provider", "A"),
                "embedding": (cfg.get("embedding") or {}).get("provider", "A"),
            },
            "compute": {"options": compute_options, "device": compute_device,
                        "activeDesc": compute_active},
            "dataRoot": data_root,
        }

    def settings_get_providers(self) -> list[dict]:
        return self._providers()

    # ---------------------------------------------------------- 模型配置
    def settings_save_api_key(self, provider_key: str, api_key: str):
        api_key = (api_key or "").strip()
        if not api_key:
            self._toast(self._tr("settings.fillApiKey"))
            return False
        try:
            self.model_config_service.set_api_key(provider_key, api_key)
            self.model_config_service.sync_default_to_config(
                self._config_path)
            self._toast(self._tr("settings.apiKeySaved"))
            return True
        except Exception as e:
            self._toast(self._tr("settings.saveFailed", msg=e), is_error=True)
            return False

    def settings_clear_api_key(self, provider_key: str):
        try:
            self.model_config_service.clear_api_key(provider_key)
            self._toast(self._tr("settings.apiKeyCleared"))
            return True
        except Exception as e:
            self._toast(self._tr("settings.clearFailed", msg=e), is_error=True)
            return False

    def settings_save_model_states(self, provider_key: str, states: dict):
        try:
            for model_name, enabled in (states or {}).items():
                self.model_config_service.set_model_enabled(
                    provider_key, model_name, bool(enabled))
            self.model_config_service.sync_default_to_config(
                self._config_path)
            self._toast(self._tr("settings.modelStatesSaved"))
            return True
        except Exception as e:
            self._toast(self._tr("settings.saveFailed", msg=e), is_error=True)
            return False

    def settings_test_connection(self, provider_key: str,
                                 api_key_from_field: str):
        from presets.llm_providers import get_provider
        provider = get_provider(provider_key)
        if provider is None:
            return False
        api_key = (api_key_from_field or "").strip() or \
            self.model_config_service.get_api_key(provider_key)
        if not api_key:
            self._toast(self._tr("settings.fillApiKey"))
            return False
        pc = self.model_config_service.get_provider_config(provider_key)
        model_name = ""
        if pc:
            for mc in pc.models:
                if mc.enabled:
                    model_name = mc.model_name
                    break
            if not model_name and pc.models:
                model_name = pc.models[0].model_name
        if not model_name:
            self._toast(self._tr("settings.noModelAvailable"))
            return False
        self._status(self._tr("settings.testing"))

        def _run():
            try:
                from openai import OpenAI
                client = OpenAI(base_url=provider.api_base, api_key=api_key,
                                timeout=15)
                resp = client.chat.completions.create(
                    model=model_name,
                    messages=[{"role": "user", "content": "ping"}],
                    max_tokens=5)
                content = resp.choices[0].message.content or ""
                self._emit("settings", "testConnectionResult",
                           {"ok": True, "msg": f"OK: {content[:50]}"})
            except Exception as e:
                self._emit("settings", "testConnectionResult",
                           {"ok": False, "msg": str(e)})

        threading.Thread(target=_run, daemon=True).start()
        return True

    def settings_open_key_apply_url(self, provider_key: str):
        from presets.llm_providers import get_provider
        provider = get_provider(provider_key)
        if provider is not None:
            self.open_external(provider.key_apply_url)

    # ---------------------------------------------------------- 默认模型
    def settings_set_default_models(self, mapping: dict):
        """批量保存默认模型 {role: [provider_key, model_name]}"""
        try:
            for role, ref in (mapping or {}).items():
                if ref and len(ref) == 2:
                    self.model_config_service.set_default_model(
                        role, ref[0], ref[1])
            self._toast(self._tr("settings.defaultsSaved"))
            return True
        except Exception as e:
            self._toast(self._tr("settings.defaultsSaveFailed", msg=e),
                        is_error=True)
            return False

    # ---------------------------------------------------------- 数据位置
    def settings_pick_data_directory(self) -> str:
        if self._window is None:
            return ""
        try:
            import webview
            result = self._window.create_file_dialog(webview.FOLDER_DIALOG)
            if result:
                return os.path.abspath(result[0])
        except Exception as e:
            logger.error(f"目录选择对话框失败: {e}")
        return ""

    def settings_migrate_data(self, new_dir: str):
        if self._migrate_running:
            return False
        try:
            from utils.paths import get_data_root
            current = get_data_root()
        except Exception:
            from utils.paths import DEFAULT_DATA_ROOT
            current = DEFAULT_DATA_ROOT
        if os.path.abspath(new_dir) == os.path.abspath(current):
            self._toast(self._tr("settings.sameLocation"))
            return False
        self._migrate_running = True
        self._emit("settings", "migrateRunning", True)
        self._status(self._tr("settings.migrating"))

        def _run():
            try:
                from utils.paths import migrate_data_root
                ok, msg = migrate_data_root(new_dir)
            except Exception as e:
                ok, msg = False, str(e)
            if ok:
                try:
                    from utils.paths import get_data_root as gdr
                    cfg = self._load_config()
                    cfg.setdefault("paths", {})["data_root"] = gdr()
                    self._save_config(cfg)
                except Exception as e:
                    logger.error(f"更新 config.yaml 失败: {e}")
            self._migrate_running = False
            self._emit("settings", "migrateRunning", False)
            self._emit("settings", "migrateFinished",
                       {"ok": ok, "msg": msg, "dataRoot": new_dir})

        threading.Thread(target=_run, daemon=True).start()
        return True

    # ---------------------------------------------------------- 凭据
    def settings_save_credentials(self, values: dict):
        from services.credential_service import CredentialService
        cred = CredentialService()
        saved = 0
        for key, val in (values or {}).items():
            if not val:
                continue
            try:
                cred.set(key, val)
                saved += 1
            except Exception as e:
                self._toast(self._tr("settings.credentialSaveFailed",
                                     key=key, msg=e), is_error=True)
                return False
        if saved:
            self._toast(self._tr("settings.credentialsSaved", count=saved))
        else:
            self._toast(self._tr("settings.noCredentialFilled"))
        return True

    def settings_clear_credentials(self):
        from services.credential_service import CredentialService
        cred = CredentialService()
        for item in cred.list_items():
            try:
                cred.delete(item.key)
            except Exception as e:
                logger.warning(f"删除凭据 {item.key} 失败: {e}")
        self._toast(self._tr("settings.credentialsCleared"))
        return True

    # ---------------------------------------------------------- 一键部署
    def settings_run_bootstrap(self):
        if self._bootstrap_running:
            self._toast(self._tr("settings.bootstrapRunning"))
            return False
        self._bootstrap_running = True
        self._emit("settings", "bootstrapRunning", True)

        def _run():
            handler = _EventLogHandler(self._emit)
            handler.setFormatter(logging.Formatter(
                "%(asctime)s [%(levelname)s] %(message)s"))
            targets = [logging.getLogger("scripts.bootstrap"),
                       logging.getLogger("scripts.init_db"),
                       logging.getLogger("utils.credentials"),
                       logging.getLogger()]
            for lg in targets:
                lg.addHandler(handler)
            try:
                from scripts.bootstrap import Bootstrap
                ok = Bootstrap(config_path=self._config_path).run()
                self._emit("settings", "bootstrapFinished",
                           {"ok": bool(ok), "msg": ""})
            except Exception as e:
                logger.error(f"Bootstrap 执行异常: {e}", exc_info=True)
                self._emit("settings", "bootstrapFinished",
                           {"ok": False, "msg": str(e)})
            finally:
                for lg in targets:
                    lg.removeHandler(handler)
                self._bootstrap_running = False
                self._emit("settings", "bootstrapRunning", False)
                self._emit("settings", "depsChanged", None)
                self._emit("settings", "credentialsChanged", None)

        threading.Thread(target=_run, daemon=True).start()
        return True

    # ---------------------------------------------------------- 依赖管理
    def settings_get_dependencies(self) -> dict:
        from services.dependency_service import DependencyService
        dep = DependencyService()
        status = dep.get_status()
        return {
            "coreDeps": [{"name": pkg, "installed": ok}
                         for pkg, ok in dep.get_core_status().items()],
            "optionalComponents": [
                {"key": c.key, "name": c.name, "description": c.description,
                 "packages": list(c.packages),
                 "installed": status.get(c.key, False)}
                for c in dep.list_components()],
        }

    def settings_run_dependency_task(self, component_keys: list,
                                     install: bool):
        keys = [str(k) for k in (component_keys or [])]
        if not keys:
            self._toast(self._tr("settings.selectComponentFirst"))
            return False
        if self._dep_running:
            self._toast(self._tr("settings.taskRunning"))
            return False
        from services.dependency_service import DependencyService
        worker = DependencyService().create_install_worker(keys,
                                                           install=install)
        worker.progress.connect(
            lambda line: self._emit("settings", "depLog", line),
            Qt.DirectConnection)
        worker.finished.connect(self._on_dep_done, Qt.DirectConnection)
        self._dep_running = True
        self._emit("settings", "depRunning", True)
        threading.Thread(target=worker.run, daemon=True).start()
        return True

    def _on_dep_done(self, ok: bool, msg: str):
        self._dep_running = False
        self._emit("settings", "depRunning", False)
        self._emit("settings", "depFinished", {"ok": bool(ok), "msg": msg})
        self._emit("settings", "depsChanged", None)

    # ---------------------------------------------------------- 方案 / 计算设备
    def settings_save_scheme(self, vlm: str, emb: str):
        try:
            cfg = self._load_config()
            cfg.setdefault("vlm", {})["provider"] = vlm
            cfg.setdefault("embedding", {})["provider"] = emb
            self._save_config(cfg)
            self._toast(self._tr("settings.scheme.savedToast"))
            return True
        except Exception as e:
            self._toast(self._tr("settings.scheme.saveFailed", msg=e),
                        is_error=True)
            return False

    def settings_set_compute_device(self, device: str):
        device = (device or "auto").strip()
        try:
            cfg = self._load_config()
            cfg.setdefault("compute", {})["device"] = device
            self._save_config(cfg)
            self._toast(self._tr("settings.compute.savedToast"))
            return True
        except Exception as e:
            self._toast(self._tr("settings.compute.saveFailed", msg=e),
                        is_error=True)
            return False
