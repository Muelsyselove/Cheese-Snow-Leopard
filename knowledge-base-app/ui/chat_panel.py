"""聊天面板 — 双栏布局：左侧对话列表 + 右侧对话窗口

功能：
- 左栏：对话列表（新建 / 切换 / 删除 / 重命名）
- 右栏：模型选择下拉框（仅已配置且已启用）+ 对话显示 + 输入框
- 对话持久化到 SQLite（ChatStore）
- 支持 RAG 模式（若 rag_service 可用）与直接对话模式
- 流式输出 + 手动中断 + 思考模式切换 + 思考过程自动折叠
- 自动命名：用所选模型为对话生成简短标题
"""
from __future__ import annotations

import logging

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextBrowser, QLineEdit, QPushButton,
    QLabel, QListWidget, QListWidgetItem, QSplitter, QComboBox, QMessageBox,
    QInputDialog, QMenu, QScrollArea,
)
from PySide6.QtCore import Signal, Slot, Qt, QPoint
from PySide6.QtGui import QTextCursor, QAction

logger = logging.getLogger(__name__)


class AssistantMessageWidget(QWidget):
    """一条 AI 回复：可折叠思考过程 + 正式回答 + 引用来源"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thinking_text = ""
        self._answer_text = ""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # 思考过程折叠按钮
        self.thinking_btn = QPushButton("⏵ 思考过程")
        self.thinking_btn.setCheckable(True)
        self.thinking_btn.setChecked(False)
        self.thinking_btn.setStyleSheet(
            "QPushButton { text-align:left; color:#b08000; background:none;"
            " border:none; font-size:12px; padding:2px; }"
            "QPushButton:hover { color:#8a6d00; }"
        )
        self.thinking_btn.clicked.connect(self._toggle_thinking)
        layout.addWidget(self.thinking_btn)

        self.thinking_body = QTextBrowser()
        self.thinking_body.setStyleSheet(
            "QTextBrowser { background:#fdf6e3; border:1px solid #e8dcc0;"
            " border-radius:4px; padding:6px; color:#7a6a3a; font-size:12px; }"
        )
        self.thinking_body.hide()
        layout.addWidget(self.thinking_body)

        # 正式回答
        self.answer_body = QTextBrowser()
        self.answer_body.setStyleSheet(
            "QTextBrowser { background:#fafafa; border:none; }"
        )
        layout.addWidget(self.answer_body)

        # 引用来源
        self.refs_body = QTextBrowser()
        self.refs_body.setStyleSheet(
            "QTextBrowser { background:transparent; border:none; }"
        )
        self.refs_body.hide()
        layout.addWidget(self.refs_body)

    # ---- 流式输入 ----
    def append_reasoning(self, text: str):
        """流式追加思考过程（生成期间显示，结束后自动折叠）"""
        self._thinking_text += text
        self._insert_at_end(self.thinking_body, text)
        if not self.thinking_body.isVisible():
            self.thinking_body.show()
            self.thinking_btn.setChecked(True)

    def append_answer(self, text: str):
        """流式追加正式回答"""
        self._answer_text += text
        self._insert_at_end(self.answer_body, text)

    def set_answer(self, text: str):
        """一次性设置正式回答（如历史加载）"""
        self._answer_text = text
        self.answer_body.setPlainText(text)
        self.answer_body.moveCursor(QTextCursor.End)

    def set_thinking(self, text: str):
        """设置思考过程（历史加载）"""
        self._thinking_text = text
        self.thinking_body.setPlainText(text)
        if text:
            self.thinking_btn.show()
            self.thinking_btn.setChecked(False)
            self.thinking_body.hide()
        else:
            self.thinking_btn.hide()

    @property
    def answer_text(self) -> str:
        return self._answer_text

    def finish_thinking(self):
        """生成结束后自动折叠思考过程"""
        if self._thinking_text:
            self.thinking_btn.setChecked(False)
            self.thinking_body.hide()

    def append_references(self, refs: list[dict]):
        """渲染引用来源"""
        if not refs:
            return
        self.refs_body.clear()
        html = ["<div style='margin-top:6px; padding:6px 10px; "
                "border-left:3px solid #4a90d9; background:#f0f6ff; "
                "font-size:12px; color:#555;'>"
                "<b>📎 引用来源：</b>"]
        for i, ref in enumerate(refs, start=1):
            source = ref.get("source_file", "未知文件")
            page = ref.get("page", "?")
            rtype = ref.get("type", "text")
            excerpt = (ref.get("excerpt", "") or "").strip()
            excerpt_html = f" — <i>{self._esc(excerpt[:120])}</i>" if excerpt else ""
            html.append(
                f"<div style='margin-top:2px;'>"
                f"[{i}] <b>{self._esc(source)}</b> "
                f"第 <b>{page}</b> 页 "
                f"<span style='color:#888'>({rtype})</span>"
                f"{excerpt_html}</div>"
            )
        html.append("</div>")
        self.refs_body.setHtml("".join(html))
        self.refs_body.show()

    def _toggle_thinking(self):
        if self._thinking_text:
            self.thinking_body.setVisible(self.thinking_btn.isChecked())

    @staticmethod
    def _insert_at_end(browser: QTextBrowser, text: str):
        cursor = browser.textCursor()
        cursor.movePosition(QTextCursor.End)
        browser.setTextCursor(cursor)
        browser.insertPlainText(text)
        sb = browser.verticalScrollBar()
        if sb is not None:
            sb.setValue(sb.maximum())

    @staticmethod
    def _esc(text: str) -> str:
        if not text:
            return ""
        return (
            str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )


class ChatPanel(QWidget):
    """聊天面板 — 双栏：左对话列表 + 右对话窗口"""

    references_ready = Signal(list)

    def __init__(self, rag_service=None, model_config_service=None,
                 chat_store=None):
        super().__init__()
        self.rag_service = rag_service
        self.model_config_service = model_config_service
        self.chat_store = chat_store
        # 当前对话 ID 与消息历史
        self._current_conv_id: int | None = None
        self.history: list[dict] = []
        # 持有 worker 引用避免被 GC
        self._search_worker = None
        self._direct_worker = None
        self._title_worker = None
        # 当前选中的模型 (provider_key, model_name, display_name)
        self._current_model: tuple[str, str, str] | None = None
        # 当前正在流式输出的 AI 消息 widget
        self._streaming_widget: AssistantMessageWidget | None = None
        # 是否正在生成回复
        self._generating = False
        # 本次回复是否被手动中断
        self._interrupted = False
        # 思考模式（默认关闭，避免对不支持思考参数/非推理模型造成请求失败）
        self._thinking = False

        self._init_ui()
        self._refresh_model_selector()
        self._refresh_conversation_list()

    # ------------------------------------------------------------------ UI
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Horizontal)

        # ---- 左栏：对话列表 ----
        left = QWidget()
        left_v = QVBoxLayout(left)
        left_v.setContentsMargins(4, 4, 4, 4)

        new_btn = QPushButton("+ 新对话")
        new_btn.clicked.connect(self._on_new_conversation)
        left_v.addWidget(new_btn)

        self.conv_list = QListWidget()
        self.conv_list.currentItemChanged.connect(self._on_conv_selected)
        self.conv_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.conv_list.customContextMenuRequested.connect(
            self._on_conv_context_menu
        )
        left_v.addWidget(self.conv_list, 1)

        splitter.addWidget(left)

        # ---- 右栏：对话窗口 ----
        right = QWidget()
        right_v = QVBoxLayout(right)
        right_v.setContentsMargins(4, 4, 4, 4)

        # 顶部工具栏：模型选择 + 自动命名
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("模型："))
        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(280)
        self.model_combo.currentIndexChanged.connect(self._on_model_changed)
        toolbar.addWidget(self.model_combo, 1)

        auto_name_btn = QPushButton("自动命名")
        auto_name_btn.clicked.connect(self._on_auto_name)
        toolbar.addWidget(auto_name_btn)

        rename_btn = QPushButton("重命名")
        rename_btn.clicked.connect(self._on_rename_conversation)
        toolbar.addWidget(rename_btn)

        right_v.addLayout(toolbar)

        # ---- 消息滚动区（消息型 widget 容器） ----
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("QScrollArea { border:none; background:#fafafa; }")
        self.message_container = QWidget()
        self.message_container.setStyleSheet("background:#fafafa;")
        self.msg_layout = QVBoxLayout(self.message_container)
        self.msg_layout.setContentsMargins(8, 8, 8, 8)
        self.msg_layout.setSpacing(12)
        self.msg_layout.addStretch(1)
        self.scroll.setWidget(self.message_container)
        right_v.addWidget(self.scroll, 1)

        # ---- 思考模式切换（输入框上方） ----
        thinking_row = QHBoxLayout()
        self.thinking_btn = QPushButton("🧠 思考模式")
        self.thinking_btn.setCheckable(True)
        self.thinking_btn.setChecked(self._thinking)
        self.thinking_btn.setToolTip("开启后，AI 将先展示思考过程（可折叠）；关闭则直接输出回答")
        self.thinking_btn.setStyleSheet(
            "QPushButton { padding:3px 10px; border:1px solid #b0b0b0;"
            " border-radius:4px; background:#ffffff; color:#333; }"
            "QPushButton:checked { border-color:#4a90d9; background:#e8f1fb;"
            " color:#1a5fa8; }"
        )
        self.thinking_btn.toggled.connect(self._on_thinking_toggled)
        thinking_row.addWidget(self.thinking_btn)
        thinking_row.addStretch(1)
        right_v.addLayout(thinking_row)

        # ---- 输入区 ----
        input_row = QHBoxLayout()
        self.input_box = QLineEdit()
        self.input_box.setPlaceholderText("输入问题，回车发送...")
        self.input_box.returnPressed.connect(self._on_send)
        self.send_btn = QPushButton("发送")
        self.send_btn.clicked.connect(self._on_send)
        self.stop_btn = QPushButton("停止")
        self.stop_btn.setEnabled(False)
        self.stop_btn.setToolTip("中断当前 AI 回复")
        self.stop_btn.clicked.connect(self._on_stop)
        input_row.addWidget(self.input_box, 1)
        input_row.addWidget(self.stop_btn)
        input_row.addWidget(self.send_btn)
        right_v.addLayout(input_row)

        # 服务未就绪提示
        if not self.model_config_service or not self.model_config_service.has_any_configured():
            hint = QLabel(
                "<i style='color:#888'>尚未配置任何模型，请先在「设置」中配置厂商 API Key 并启用模型。</i>"
            )
            hint.setContentsMargins(8, 4, 8, 4)
            right_v.addWidget(hint)

        splitter.addWidget(right)
        splitter.setSizes([260, 740])
        layout.addWidget(splitter, 1)

    # ---------------------------------------------------------- 模型选择
    def _refresh_model_selector(self):
        """刷新模型下拉框（仅已配置且已启用的模型）"""
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        if self.model_config_service is None:
            self.model_combo.addItem("（未配置模型服务）", None)
            self.model_combo.setEnabled(False)
            self._current_model = None
            self.model_combo.blockSignals(False)
            return

        models = self.model_config_service.list_enabled_models()
        if not models:
            self.model_combo.addItem("（暂无已启用模型，请到设置页配置）", None)
            self.model_combo.setEnabled(False)
            self._current_model = None
            self.model_combo.blockSignals(False)
            return

        self.model_combo.setEnabled(True)
        for provider_key, provider_name, model_name, model_display in models:
            label = f"[{provider_name}] {model_display}"
            data = (provider_key, model_name, model_display)
            self.model_combo.addItem(label, data)
        # 默认选第一个
        self.model_combo.setCurrentIndex(0)
        self._current_model = self.model_combo.itemData(0)
        self.model_combo.blockSignals(False)

    @Slot()
    def refresh_models(self):
        """供外部调用：模型配置变更后刷新下拉框"""
        self._refresh_model_selector()

    def _on_model_changed(self):
        data = self.model_combo.currentData()
        self._current_model = data
        # 记录到当前对话
        if data and self._current_conv_id and self.chat_store:
            self.chat_store.set_conversation_model(
                self._current_conv_id, data[1]
            )

    def _get_llm_client(self):
        """根据当前选中模型创建 LLM 客户端"""
        if self._current_model is None or self.model_config_service is None:
            return None
        provider_key, model_name, _ = self._current_model
        try:
            return self.model_config_service.create_llm_client(
                provider_key, model_name
            )
        except Exception as e:
            logger.error(f"创建 LLM 客户端失败: {e}")
            return None

    @Slot(bool)
    def _on_thinking_toggled(self, checked: bool):
        self._thinking = checked

    # ---------------------------------------------------------- 对话列表
    def _refresh_conversation_list(self):
        """刷新左侧对话列表"""
        self.conv_list.blockSignals(True)
        self.conv_list.clear()
        if self.chat_store is None:
            self.conv_list.blockSignals(False)
            return
        for conv in self.chat_store.list_conversations():
            label = conv.title or "新对话"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, conv.id)
            self.conv_list.addItem(item)
        # 选中当前对话
        if self._current_conv_id is not None:
            self._select_conversation(self._current_conv_id)
        self.conv_list.blockSignals(False)

    def _select_conversation(self, conv_id: int):
        for i in range(self.conv_list.count()):
            item = self.conv_list.item(i)
            if item.data(Qt.UserRole) == conv_id:
                self.conv_list.setCurrentRow(i)
                break

    @Slot()
    def _on_new_conversation(self):
        """创建新对话"""
        if self.chat_store is None:
            QMessageBox.information(self, "提示", "对话存储未就绪")
            return
        conv = self.chat_store.create_conversation(title="新对话")
        self._current_conv_id = conv.id
        self.history = []
        self._clear_messages()
        self._refresh_conversation_list()
        self._select_conversation(conv.id)
        self.input_box.setFocus()

    def _on_conv_selected(self, current: QListWidgetItem,
                          previous: QListWidgetItem):
        if current is None:
            return
        conv_id = current.data(Qt.UserRole)
        self._load_conversation(conv_id)

    def _load_conversation(self, conv_id: int):
        """加载指定对话的消息"""
        if self.chat_store is None:
            return
        conv = self.chat_store.get_conversation(conv_id)
        if conv is None:
            return
        self._current_conv_id = conv_id
        self._clear_messages()
        self.history = []
        messages = self.chat_store.list_messages(conv_id)
        for msg in messages:
            self.history.append({"role": msg.role, "content": msg.content})
            if msg.role == "user":
                self._add_user_message(msg.content)
            elif msg.role == "assistant":
                w = self._add_assistant_message()
                w.set_answer(msg.content)
        self._scroll_to_bottom()
        # 匹配对话记录的模型到下拉框
        if conv.model:
            self._match_model_combo(conv.model)

    def _match_model_combo(self, model_name: str):
        """根据模型名匹配下拉框选项"""
        for i in range(self.model_combo.count()):
            data = self.model_combo.itemData(i)
            if data and data[1] == model_name:
                self.model_combo.blockSignals(True)
                self.model_combo.setCurrentIndex(i)
                self._current_model = data
                self.model_combo.blockSignals(False)
                return

    def _on_conv_context_menu(self, pos: QPoint):
        """对话列表右键菜单"""
        item = self.conv_list.itemAt(pos)
        if item is None:
            return
        conv_id = item.data(Qt.UserRole)
        menu = QMenu(self)
        rename_act = QAction("重命名", self)
        rename_act.triggered.connect(lambda: self._rename_conv(conv_id))
        delete_act = QAction("删除对话", self)
        delete_act.triggered.connect(lambda: self._delete_conv(conv_id))
        menu.addAction(rename_act)
        menu.addAction(delete_act)
        menu.exec(self.conv_list.mapToGlobal(pos))

    def _rename_conv(self, conv_id: int):
        if self.chat_store is None:
            return
        conv = self.chat_store.get_conversation(conv_id)
        if conv is None:
            return
        text, ok = QInputDialog.getText(
            self, "重命名对话", "新名称：", text=conv.title
        )
        if ok and text.strip():
            self.chat_store.rename_conversation(conv_id, text.strip())
            self._refresh_conversation_list()

    def _delete_conv(self, conv_id: int):
        if self.chat_store is None:
            return
        reply = QMessageBox.question(
            self, "确认", "确认删除该对话？此操作不可恢复。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        self.chat_store.delete_conversation(conv_id)
        if self._current_conv_id == conv_id:
            self._current_conv_id = None
            self.history = []
            self._clear_messages()
        self._refresh_conversation_list()

    @Slot()
    def _on_rename_conversation(self):
        if self._current_conv_id is None:
            QMessageBox.information(self, "提示", "请先选择一个对话")
            return
        self._rename_conv(self._current_conv_id)

    # ---------------------------------------------------------- 消息容器
    def _clear_messages(self):
        """清空消息展示区"""
        while self.msg_layout.count() > 1:  # 保留末尾 stretch
            item = self.msg_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._streaming_widget = None

    def _add_user_message(self, text: str):
        """添加一条用户消息"""
        label = QLabel(
            f"<div style='text-align:right;'><span style='background:#e8f1fb;"
            f" padding:6px 10px; border-radius:6px; color:#1a5fa8;'>"
            f"{self._esc(text)}</span></div>"
        )
        label.setWordWrap(True)
        self.msg_layout.insertWidget(self.msg_layout.count() - 1, label)
        self._scroll_to_bottom()

    def _add_assistant_message(self) -> AssistantMessageWidget:
        """添加一条 AI 消息 widget，返回它"""
        header = QLabel(
            "<div style='color:#333;'><b>助手：</b></div>"
        )
        w = AssistantMessageWidget()
        self.msg_layout.insertWidget(self.msg_layout.count() - 1, header)
        self.msg_layout.insertWidget(self.msg_layout.count() - 1, w)
        self._scroll_to_bottom()
        return w

    def _scroll_to_bottom(self):
        sb = self.scroll.verticalScrollBar()
        if sb is not None:
            sb.setValue(sb.maximum())

    # ---------------------------------------------------------- 发送消息
    @Slot()
    def _on_send(self):
        # AI 回复期间禁止发送，需等待结束或手动终止
        if self._generating:
            self.input_box.setFocus()
            return
        question = self.input_box.text().strip()
        if not question:
            return

        if self._current_conv_id is None and self.chat_store is not None:
            # 自动创建新对话
            conv = self.chat_store.create_conversation(title="新对话")
            self._current_conv_id = conv.id
            self._refresh_conversation_list()
            self._select_conversation(conv.id)

        llm = self._get_llm_client()
        if llm is None and self.rag_service is None:
            self._add_user_message(question)
            self._add_error_message(
                "未选择模型且 RAG 服务不可用。请先在「设置」中配置模型。"
            )
            return

        # 显示用户消息
        self._add_user_message(question)
        self.input_box.clear()
        self.history.append({"role": "user", "content": question})

        # 持久化用户消息
        if self.chat_store and self._current_conv_id:
            self.chat_store.add_message(
                self._current_conv_id, "user", question
            )

        # 进入生成状态
        self._interrupted = False
        self._set_generating(True)

        # 优先使用 RAG（需 rag_service 且 embedder/qdrant 就绪）
        if self.rag_service is not None:
            from workers.search_worker import SearchWorker
            self._search_worker = SearchWorker(
                self.rag_service, question, self.history, llm=llm,
                thinking=self._thinking,
            )
            self._search_worker.reasoning_stream.connect(
                self._on_reasoning_stream
            )
            self._search_worker.token_stream.connect(self._on_token_stream)
            self._search_worker.finished.connect(self._on_search_done)
            self._search_worker.error.connect(self._on_search_error)
            self._search_worker.start()
        else:
            # 直接对话模式
            from workers.llm_worker import DirectChatWorker
            self._direct_worker = DirectChatWorker(
                llm, self.history, thinking=self._thinking
            )
            self._direct_worker.reasoning_stream.connect(
                self._on_reasoning_stream
            )
            self._direct_worker.token_stream.connect(self._on_token_stream)
            self._direct_worker.finished.connect(self._on_direct_done)
            self._direct_worker.error.connect(self._on_search_error)
            self._direct_worker.start()

    def _set_generating(self, generating: bool):
        """切换生成状态：控制发送/停止按钮与输入框可用性"""
        self._generating = generating
        self.send_btn.setEnabled(not generating)
        self.input_box.setEnabled(not generating)
        self.stop_btn.setEnabled(generating)
        if generating:
            # 创建新的 AI 消息 widget 用于流式输出
            self._streaming_widget = self._add_assistant_message()
        else:
            self._streaming_widget = None

    @Slot(str)
    def _on_reasoning_stream(self, text: str):
        if self._streaming_widget is not None:
            self._streaming_widget.append_reasoning(text)
            self._scroll_to_bottom()

    @Slot(str)
    def _on_token_stream(self, text: str):
        if self._streaming_widget is not None:
            self._streaming_widget.append_answer(text)
            self._scroll_to_bottom()

    @Slot()
    def _on_stop(self):
        """手动中断 AI 回复"""
        self._interrupted = True
        if self._search_worker is not None:
            self._search_worker.cancel()
        if self._direct_worker is not None:
            self._direct_worker.cancel()
        # 中断后立即结束生成状态（不保存部分答案）
        self._finalize_stream("")

    def _finalize_stream(self, answer: str):
        """结束一次流式生成：折叠思考、持久化、恢复输入"""
        widget = self._streaming_widget
        if widget is not None:
            widget.finish_thinking()
        if answer and not self._interrupted:
            self.history.append({"role": "assistant", "content": answer})
            if self.chat_store and self._current_conv_id:
                self.chat_store.add_message(
                    self._current_conv_id, "assistant", answer
                )
        self._set_generating(False)
        self._search_worker = None
        self._direct_worker = None

    @Slot(dict)
    def _on_search_done(self, result):
        answer = result.get("answer", "")
        retrieved = result.get("retrieved_chunks", []) or []

        refs: list[dict] = []
        # 若已手动中断，则不渲染引用、不保存
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

        if self._streaming_widget is not None:
            self._streaming_widget.append_references(refs)
        self._finalize_stream(answer)
        self.references_ready.emit(refs)

    @Slot(str)
    def _on_direct_done(self, answer: str):
        self._finalize_stream(answer)

    @Slot(str)
    def _on_search_error(self, msg: str):
        self._add_error_message(f"请求失败: {msg}")
        self._finalize_stream("")

    def _add_error_message(self, text: str):
        label = QLabel(
            f"<div style='color:#c00;'><i>{self._esc(text)}</i></div>"
        )
        label.setWordWrap(True)
        self.msg_layout.insertWidget(self.msg_layout.count() - 1, label)
        self._scroll_to_bottom()

    # ---------------------------------------------------------- 自动命名
    @Slot()
    def _on_auto_name(self):
        """用当前所选模型为对话生成标题"""
        if self._current_conv_id is None:
            QMessageBox.information(self, "提示", "请先选择或创建一个对话")
            return
        if not self.history:
            QMessageBox.information(self, "提示", "对话尚无内容，无法命名")
            return
        llm = self._get_llm_client()
        if llm is None:
            QMessageBox.warning(self, "提示", "请先选择一个已配置的模型")
            return
        # 取第一轮 user + assistant
        user_msg = ""
        assistant_msg = ""
        for m in self.history:
            if m["role"] == "user" and not user_msg:
                user_msg = m["content"]
            elif m["role"] == "assistant" and not assistant_msg:
                assistant_msg = m["content"]
            if user_msg and assistant_msg:
                break
        if not user_msg:
            QMessageBox.information(self, "提示", "无用户消息可用于命名")
            return

        from workers.llm_worker import TitleWorker
        self._title_worker = TitleWorker(llm, user_msg, assistant_msg)
        self._title_worker.finished.connect(self._on_title_done)
        self._title_worker.error.connect(self._on_title_error)
        self._title_worker.start()

    @Slot(str)
    def _on_title_done(self, title: str):
        if self._current_conv_id and self.chat_store:
            self.chat_store.rename_conversation(self._current_conv_id, title)
            self._refresh_conversation_list()
        self._title_worker = None

    @Slot(str)
    def _on_title_error(self, msg: str):
        QMessageBox.warning(self, "命名失败", f"自动命名失败: {msg}")
        self._title_worker = None

    @staticmethod
    def _esc(text: str) -> str:
        """HTML 转义"""
        if not text:
            return ""
        return (
            str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )