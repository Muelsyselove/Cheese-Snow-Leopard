"""对话桥接层 — 将 ChatStore / ModelConfigService / RAG Worker 暴露给 QML

消息流式协议（QML 监听）：
    userMessageAppended(text)        用户消息上屏
    assistantMessageStarted()        AI 消息气泡创建（流式开始）
    reasoningChunk(text)             思考过程增量
    answerChunk(text)                正式回答增量
    stepsUpdated(list)               步骤时间线更新（思考/检索/回答 多步状态）
    referencesAppended(list)         引用来源（流式末尾）
    streamFinished()                 流式结束（折叠思考、恢复输入）
    assistantError(text)             错误消息上屏
"""
from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Property, Signal, Slot

logger = logging.getLogger(__name__)


class ChatBridge(QObject):
    """对话页桥接 — 复刻旧 ChatPanel 全部交互逻辑"""

    # 会话列表 / 消息流信号
    conversationsChanged = Signal()
    messagesCleared = Signal()
    historyMessageAppended = Signal(str, str)      # role, content
    userMessageAppended = Signal(str)
    assistantMessageStarted = Signal()
    reasoningChunk = Signal(str)
    answerChunk = Signal(str)
    stepsUpdated = Signal(list)                    # [{kind, status, detail}]
    referencesAppended = Signal(list)
    streamFinished = Signal()
    assistantError = Signal(str)

    # 状态信号
    generatingChanged = Signal()
    thinkingChanged = Signal()
    modelsChanged = Signal()
    currentModelChanged = Signal()
    titleUpdated = Signal(int, str)                # conv_id, new_title
    infoMessage = Signal(str)                      # 轻提示（toast）
    statusMessage = Signal(str)                    # 状态栏

    def __init__(self, rag_service=None, model_config_service=None,
                 chat_store=None, i18n=None, parent=None):
        super().__init__(parent)
        self.rag_service = rag_service
        self.model_config_service = model_config_service
        self.chat_store = chat_store
        self._i18n = i18n

        self._current_conv_id: int | None = None
        self.history: list[dict] = []
        self._current_model: tuple[str, str, str] | None = None  # (pk, model, display)
        self._generating = False
        self._interrupted = False
        self._thinking = False
        # 当前流式的步骤时间线 [{kind: thinking|search|answer, status: running|done, detail}]
        self._steps: list[dict] = []

        # worker 引用（防 GC）
        self._search_worker = None
        self._direct_worker = None
        self._title_worker = None

        self._select_default_model()

    def _tr(self, key: str, **params) -> str:
        if self._i18n is None:
            return key
        if params:
            return self._i18n.trf(key, params)
        return self._i18n.tr(key)

    # ---------------------------------------------------------- 属性
    @Property("QVariantList", notify=conversationsChanged)
    def conversations(self) -> list[dict]:
        if self.chat_store is None:
            return []
        return [
            {"convId": c.id, "title": c.title or self._tr("chat.newConversationTitle"),
             "autoName": bool(c.auto_name)}
            for c in self.chat_store.list_conversations()
        ]

    @Property(int, notify=conversationsChanged)
    def currentConvId(self) -> int:
        return self._current_conv_id or -1

    @Property(bool, notify=generatingChanged)
    def generating(self) -> bool:
        return self._generating

    @Property(bool, notify=thinkingChanged)
    def thinking(self) -> bool:
        return self._thinking

    @thinking.setter
    def thinking(self, value: bool):
        if value != self._thinking:
            self._thinking = value
            self.thinkingChanged.emit()

    @Property("QVariantList", notify=modelsChanged)
    def models(self) -> list[dict]:
        if self.model_config_service is None:
            return []
        return [
            {"providerKey": pk, "providerName": pn,
             "modelName": mn, "displayName": md,
             "label": f"[{pn}] {md}"}
            for pk, pn, mn, md in self.model_config_service.list_enabled_models()
        ]

    @Property(str, notify=currentModelChanged)
    def currentModelName(self) -> str:
        return self._current_model[2] if self._current_model else ""

    @Property(bool, notify=modelsChanged)
    def hasConfiguredModel(self) -> bool:
        return bool(self.models)

    # ---------------------------------------------------------- 模型选择
    def _select_default_model(self):
        """启动时选择默认对话模型（否则第一个已启用模型）"""
        models = self.models
        if not models:
            self._current_model = None
            return
        default = None
        if self.model_config_service is not None:
            default = self.model_config_service.get_default_models().get("chat")
        if default:
            for m in models:
                if m["providerKey"] == default[0] and m["modelName"] == default[1]:
                    self._current_model = (m["providerKey"], m["modelName"], m["displayName"])
                    return
        first = models[0]
        self._current_model = (first["providerKey"], first["modelName"], first["displayName"])

    @Slot()
    def reloadModels(self):
        """模型配置变更后（设置页保存）刷新模型列表"""
        if self.model_config_service is not None:
            self.model_config_service.load()
        self._select_default_model()
        self.modelsChanged.emit()
        self.currentModelChanged.emit()

    @Slot(str, str, str)
    def selectModel(self, provider_key: str, model_name: str, display_name: str):
        """应用所选模型并记录到当前对话"""
        self._current_model = (provider_key, model_name, display_name)
        self.currentModelChanged.emit()
        if self._current_conv_id and self.chat_store:
            self.chat_store.set_conversation_model(self._current_conv_id, model_name)

    def _match_model(self, model_name: str):
        """按模型名匹配（加载历史对话时）"""
        for m in self.models:
            if m["modelName"] == model_name:
                self._current_model = (m["providerKey"], m["modelName"], m["displayName"])
                self.currentModelChanged.emit()
                return

    def _get_llm_client(self):
        if self._current_model is None or self.model_config_service is None:
            return None
        try:
            return self.model_config_service.create_llm_client(
                self._current_model[0], self._current_model[1]
            )
        except Exception as e:
            logger.error(f"创建 LLM 客户端失败: {e}")
            return None

    # ---------------------------------------------------------- 会话管理
    @Slot(result=int)
    def newConversation(self) -> int:
        if self.chat_store is None:
            self.infoMessage.emit(self._tr("chat.chatStoreNotReady"))
            return -1
        conv = self.chat_store.create_conversation(
            title=self._tr("chat.newConversationTitle"))
        self._current_conv_id = conv.id
        self.history = []
        self.messagesCleared.emit()
        self.conversationsChanged.emit()
        return conv.id

    @Slot(int)
    def selectConversation(self, conv_id: int):
        if self.chat_store is None:
            return
        conv = self.chat_store.get_conversation(conv_id)
        if conv is None:
            return
        self._current_conv_id = conv_id
        self.history = []
        self.messagesCleared.emit()
        for msg in self.chat_store.list_messages(conv_id):
            self.history.append({"role": msg.role, "content": msg.content})
            if msg.role in ("user", "assistant"):
                self.historyMessageAppended.emit(msg.role, msg.content)
        self.conversationsChanged.emit()
        if conv.model:
            self._match_model(conv.model)

    @Slot(int)
    def deleteConversation(self, conv_id: int):
        if self.chat_store is None:
            return
        self.chat_store.delete_conversation(conv_id)
        if self._current_conv_id == conv_id:
            self._current_conv_id = None
            self.history = []
            self.messagesCleared.emit()
        self.conversationsChanged.emit()

    @Slot(int, str)
    def renameConversation(self, conv_id: int, title: str):
        if self.chat_store is None or not title.strip():
            return
        self.chat_store.rename_conversation(conv_id, title.strip())
        self.conversationsChanged.emit()

    @Slot(int, bool)
    def setAutoName(self, conv_id: int, enabled: bool):
        if self.chat_store is not None:
            self.chat_store.set_auto_name(conv_id, enabled)
            self.conversationsChanged.emit()

    @Slot(int, result="QVariantMap")
    def getConversationInfo(self, conv_id: int) -> dict:
        if self.chat_store is None:
            return {}
        conv = self.chat_store.get_conversation(conv_id)
        if conv is None:
            return {}
        return {"convId": conv.id, "title": conv.title, "autoName": bool(conv.auto_name)}

    # ---------------------------------------------------------- 发送 / 中断
    @Slot(str)
    def send(self, text: str):
        question = (text or "").strip()
        if not question or self._generating:
            return

        if self._current_conv_id is None and self.chat_store is not None:
            conv = self.chat_store.create_conversation(
                title=self._tr("chat.newConversationTitle"))
            self._current_conv_id = conv.id
            self.conversationsChanged.emit()

        llm = self._get_llm_client()
        if llm is None and self.rag_service is None:
            self.userMessageAppended.emit(question)
            self.assistantError.emit(self._tr("chat.noModelNoRag"))
            return

        self.userMessageAppended.emit(question)
        self.history.append({"role": "user", "content": question})
        if self.chat_store and self._current_conv_id:
            self.chat_store.add_message(self._current_conv_id, "user", question)

        self._interrupted = False
        self._steps = []
        self._set_generating(True)

        if self.rag_service is not None:
            from workers.search_worker import SearchWorker
            self._search_worker = SearchWorker(
                self.rag_service, question, self.history, llm=llm,
                thinking=self._thinking,
            )
            self._search_worker.reasoning_stream.connect(self._on_reasoning)
            self._search_worker.token_stream.connect(self._on_token)
            self._search_worker.step_event.connect(self._on_step_event)
            self._search_worker.finished.connect(self._on_search_done)
            self._search_worker.error.connect(self._on_error)
            self._search_worker.start()
        else:
            from workers.llm_worker import DirectChatWorker
            self._direct_worker = DirectChatWorker(llm, self.history,
                                                   thinking=self._thinking)
            self._direct_worker.reasoning_stream.connect(self._on_reasoning)
            self._direct_worker.token_stream.connect(self._on_token)
            self._direct_worker.finished.connect(self._on_direct_done)
            self._direct_worker.error.connect(self._on_error)
            self._direct_worker.start()

    @Slot()
    def stop(self):
        """手动中断 AI 回复"""
        self._interrupted = True
        if self._search_worker is not None:
            self._search_worker.cancel()
        if self._direct_worker is not None:
            self._direct_worker.cancel()
        self._finalize_stream("")

    def _set_generating(self, generating: bool):
        self._generating = generating
        if generating:
            self.assistantMessageStarted.emit()
        self.generatingChanged.emit()

    def _on_reasoning(self, text: str):
        # 每轮思考追加一个步骤（agent 多轮循环时形成多步时间线）
        if not self._steps or self._steps[-1]["kind"] != "thinking" \
                or self._steps[-1]["status"] != "running":
            self._steps.append({"kind": "thinking", "status": "running", "detail": ""})
            self.stepsUpdated.emit(list(self._steps))
        self.reasoningChunk.emit(text)

    def _on_token(self, text: str):
        # 首个回答 token：关闭进行中的思考步骤，开启回答步骤
        changed = False
        if self._steps and self._steps[-1]["kind"] == "thinking" \
                and self._steps[-1]["status"] == "running":
            self._steps[-1]["status"] = "done"
            changed = True
        if not any(s["kind"] == "answer" for s in self._steps):
            self._steps.append({"kind": "answer", "status": "running", "detail": ""})
            changed = True
        if changed:
            self.stepsUpdated.emit(list(self._steps))
        self.answerChunk.emit(text)

    def _on_step_event(self, event: dict):
        """检索等后端步骤事件：{"op": start|done, "kind": str, "detail": ...}"""
        op = event.get("op")
        kind = event.get("kind", "")
        if op == "start":
            # 工具调用意味着本轮思考结束
            self._close_running_step("thinking")
            self._steps.append({"kind": kind, "status": "running",
                                "detail": str(event.get("detail", ""))})
        elif op == "done":
            for s in reversed(self._steps):
                if s["kind"] == kind and s["status"] == "running":
                    s["status"] = "done"
                    s["detail"] = event.get("detail", "")
                    break
        self.stepsUpdated.emit(list(self._steps))

    def _close_running_step(self, kind: str):
        for s in reversed(self._steps):
            if s["kind"] == kind and s["status"] == "running":
                s["status"] = "done"
                return

    def _finalize_stream(self, answer: str):
        if answer and not self._interrupted:
            self.history.append({"role": "assistant", "content": answer})
            if self.chat_store and self._current_conv_id:
                self.chat_store.add_message(
                    self._current_conv_id, "assistant", answer)
            self._maybe_auto_name()
        # 关闭所有进行中的步骤（含手动中断场景）
        any_running = False
        for s in self._steps:
            if s["status"] == "running":
                s["status"] = "done"
                any_running = True
        if any_running:
            self.stepsUpdated.emit(list(self._steps))
        self._set_generating(False)
        self.streamFinished.emit()
        self._search_worker = None
        self._direct_worker = None

    def _on_search_done(self, result: dict):
        answer = result.get("answer", "")
        retrieved = result.get("retrieved_chunks", []) or []
        refs: list[dict] = []
        if not self._interrupted:
            try:
                from services.trace_service import (
                    trace_references, trace_references_fallback,
                )
                refs = trace_references(answer, retrieved)
                if not refs and retrieved:
                    refs = trace_references_fallback(answer, retrieved)
            except Exception:
                pass
        if refs:
            self.referencesAppended.emit(refs)
        self._finalize_stream(answer)

    def _on_direct_done(self, answer: str):
        self._finalize_stream(answer)

    def _on_error(self, msg: str):
        self.assistantError.emit(self._tr("chat.requestFailed", msg=msg))
        self._finalize_stream("")

    # ---------------------------------------------------------- 自动命名
    def _get_auto_naming_client(self):
        if self.model_config_service is None:
            return None
        try:
            rt = self.model_config_service.get_default_model_for_role("auto_naming")
            if rt:
                api_base, model_name, api_key = rt
                from adapters.openai_llm import OpenAILLMClient
                return OpenAILLMClient(
                    api_base=api_base, api_key=api_key, model=model_name,
                    temperature=0.3, max_tokens=4096, timeout=60,
                )
        except Exception as e:
            logger.warning(f"使用自动命名模型失败，回退当前模型: {e}")
        return self._get_llm_client()

    @Slot(int)
    def reAutoName(self, conv_id: int):
        """为指定对话重新生成标题（对话设置对话框调用）"""
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
            self.infoMessage.emit(self._tr("chat.noContentToName"))
            return
        llm = self._get_auto_naming_client()
        if llm is None:
            self.infoMessage.emit(self._tr("chat.configModelFirst"))
            return
        from workers.llm_worker import TitleWorker
        self._title_worker = TitleWorker(llm, user_msg, assistant_msg)
        self._title_worker.finished.connect(
            lambda title, cid=conv_id: self._on_title_done(title, cid))
        self._title_worker.error.connect(self._on_title_error)
        self._title_worker.start()

    def _maybe_auto_name(self):
        if self._current_conv_id is None or self.chat_store is None:
            return
        conv = self.chat_store.get_conversation(self._current_conv_id)
        if conv is None or not conv.auto_name:
            return
        if conv.title and conv.title != self._tr("chat.newConversationTitle") \
                and conv.title != "新对话":
            return
        self.reAutoName(self._current_conv_id)

    def _on_title_done(self, title: str, conv_id: int):
        if self.chat_store:
            self.chat_store.rename_conversation(conv_id, title)
            self.titleUpdated.emit(conv_id, title)
            self.conversationsChanged.emit()
        self._title_worker = None

    def _on_title_error(self, msg: str):
        self.infoMessage.emit(self._tr("chat.autoNameFailed", msg=msg))
        self._title_worker = None
