/* ============================================================
   对话页 — 会话管理 / 流式输出 / 步骤时间线 / 引用来源 / 模型选择
   ============================================================ */
"use strict";

const ChatPage = {
  convId: -1,
  conversations: [],
  models: [],
  currentModel: null,
  generating: false,
  thinking: true,
  hasRag: false,
  messages: [],          // [{role, content}] 已完成消息
  stream: null,          // 当前流式气泡引用
  els: {},

  // ---------------------------------------------------------- 初始化
  async init() {
    const root = document.getElementById("page-chat");
    root.innerHTML = `
      <div class="chat-sidebar glass">
        <button id="conv-new" class="btn btn-primary"></button>
        <div class="conv-list" id="conv-list"></div>
      </div>
      <div class="chat-main glass">
        <div class="chat-toolbar">
          <button id="model-btn" class="btn model-btn"></button>
          <button id="thinking-toggle" class="pill-toggle"></button>
          <div class="toolbar-spacer"></div>
        </div>
        <div class="chat-scroll" id="chat-scroll"></div>
        <div class="chat-input-row">
          <textarea id="chat-input" class="input chat-input" rows="1"></textarea>
          <button id="chat-send" class="btn btn-primary"></button>
          <button id="chat-stop" class="btn btn-danger hidden"></button>
        </div>
      </div>`;
    this.els = {
      list: document.getElementById("conv-list"),
      scroll: document.getElementById("chat-scroll"),
      input: document.getElementById("chat-input"),
      send: document.getElementById("chat-send"),
      stop: document.getElementById("chat-stop"),
      modelBtn: document.getElementById("model-btn"),
      thinkToggle: document.getElementById("thinking-toggle"),
      newConv: document.getElementById("conv-new"),
    };
    this.els.newConv.onclick = () => this.newConversation();
    this.els.send.onclick = () => this.send();
    this.els.stop.onclick = () => api("chat_stop");
    this.els.modelBtn.onclick = () => this.openModelPicker();
    this.els.thinkToggle.onclick = () => {
      this.thinking = !this.thinking;
      this.renderThinkingToggle();
    };
    this.els.input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
        e.preventDefault();
        this.send();
      }
    });
    this.els.input.addEventListener("input", () => {
      const ta = this.els.input;
      // 高度上限由 CSS .chat-input 的 max-height 约束，此处仅按内容伸展
      ta.style.height = "auto";
      ta.style.height = ta.scrollHeight + "px";
    });

    this.bindEvents();
    this.refreshTexts();
    await this.loadState();
  },

  refreshTexts() {
    if (!this.els.newConv) return;
    this.els.newConv.textContent = "💬 " + t("chat.newConversation");
    this.els.send.textContent = t("chat.send");
    this.els.stop.textContent = t("chat.stop");
    this.els.input.placeholder = t("chat.placeholder");
    this.renderThinkingToggle();
    this.renderModelBtn();
    this.renderConvList();
    if (!this.messages.length && !this.generating) this.renderEmpty();
  },

  rerender() { this.refreshTexts(); },

  // ---------------------------------------------------------- 状态加载
  async loadState() {
    const st = await api("chat_get_state");
    this.conversations = st.conversations || [];
    this.convId = st.currentConvId || -1;
    this.models = st.models || [];
    this.currentModel = st.currentModel;
    this.generating = !!st.generating;
    this.hasRag = !!st.hasRag;
    this.renderConvList();
    this.renderModelBtn();
    this.renderGenerating();
    if (this.convId > 0) {
      // 恢复当前会话消息
      const r = await api("chat_select_conversation", this.convId);
      this.messages = r.messages || [];
      this.renderMessages();
    }
  },

  onShow() {},

  // ---------------------------------------------------------- 事件绑定
  bindEvents() {
    Bus.on("chat", "conversationsChanged", (list) => {
      this.conversations = list || [];
      this.renderConvList();
    });
    Bus.on("chat", "userMessageAppended", (text) => {
      this.messages.push({ role: "user", content: text });
      this.clearEmpty();
      this.appendUserBubble(text);
      this.scrollBottom(true);
    });
    Bus.on("chat", "assistantMessageStarted", () => this.startAssistantBubble());
    Bus.on("chat", "reasoningChunk", (text) => this.appendReasoning(text));
    Bus.on("chat", "answerChunk", (text) => this.appendAnswer(text));
    Bus.on("chat", "stepsUpdated", (steps) => this.renderSteps(steps));
    Bus.on("chat", "referencesAppended", (refs) => this.appendRefs(refs));
    Bus.on("chat", "assistantError", (msg) => this.appendError(msg));
    Bus.on("chat", "streamFinished", () => this.finishStream());
    Bus.on("chat", "generatingChanged", (b) => {
      this.generating = !!b;
      this.renderGenerating();
    });
    Bus.on("chat", "titleUpdated", (p) => {
      const c = this.conversations.find((x) => x.convId === p.convId);
      if (c) { c.title = p.title; this.renderConvList(); }
    });
  },

  // ---------------------------------------------------------- 会话列表
  renderConvList() {
    const list = this.els.list;
    if (!list) return;
    list.innerHTML = "";
    this.conversations.forEach((c) => {
      const item = el("div", "conv-item" + (c.convId === this.convId ? " active" : ""));
      const title = el("div", "conv-title", c.title);
      const more = el("button", "conv-more", "⋯");
      more.title = t("chat.convSettings");
      more.onclick = (e) => { e.stopPropagation(); this.openConvSettings(c.convId); };
      item.appendChild(title);
      item.appendChild(more);
      item.onclick = () => this.selectConversation(c.convId);
      list.appendChild(item);
    });
  },

  async newConversation() {
    if (this.generating) return;
    const id = await api("chat_new_conversation");
    if (id > 0) {
      this.convId = id;
      this.messages = [];
      this.renderEmpty();
      this.renderConvList();
    }
  },

  async selectConversation(id) {
    if (this.generating || id === this.convId) return;
    const r = await api("chat_select_conversation", id);
    this.convId = id;
    this.messages = r.messages || [];
    this.renderMessages();
    this.renderConvList();
    // 会话模型可能切换，刷新模型按钮
    const st = await api("chat_get_state");
    this.currentModel = st.currentModel;
    this.renderModelBtn();
  },

  async openConvSettings(convId) {
    const info = await api("chat_get_conversation_info", convId);
    if (!info || !info.convId) return;
    const body = el("div");
    body.innerHTML = `
      <div class="form-row">
        <span class="switch ${info.autoName ? "on" : ""}" id="cs-autoname"></span>
        <span>${escapeHtml(t("chat.autoName"))}</span>
      </div>
      <div class="hint-xs mb-m">${escapeHtml(t("chat.autoNameTip"))}</div>
      <div class="form-row">
        <span class="text-sub">${escapeHtml(t("chat.manualName"))}</span>
      </div>
      <div class="form-row">
        <input id="cs-title" class="input form-grow" value="${escapeHtml(info.title || "")}" placeholder="${escapeHtml(t("chat.manualNamePlaceholder"))}">
        <button id="cs-rename" class="btn">${escapeHtml(t("chat.nameIt"))}</button>
      </div>`;
    const m = openModal({
      title: t("chat.convSettings"),
      body,
      actions: [
        { label: t("common.delete"), danger: true, onClick: async (close) => {
            close();
            const ok = await confirmDialog(t("chat.deleteConfirm"),
              { danger: true, okLabel: t("common.delete") });
            if (ok) {
              await api("chat_delete_conversation", convId);
              if (this.convId === convId) {
                this.convId = -1; this.messages = []; this.renderEmpty();
              }
            }
            return false;
          } },
        { label: t("chat.reAutoName"), onClick: () => api("chat_re_auto_name", convId) },
        { label: t("common.close"), primary: true },
      ],
    });
    body.querySelector("#cs-autoname").onclick = async (e) => {
      const sw = e.currentTarget;
      const on = !sw.classList.contains("on");
      sw.classList.toggle("on", on);
      await api("chat_set_auto_name", convId, on);
    };
    body.querySelector("#cs-rename").onclick = async () => {
      const v = body.querySelector("#cs-title").value.trim();
      if (v) { await api("chat_rename_conversation", convId, v); m.close(); }
    };
  },

  // ---------------------------------------------------------- 模型选择
  renderModelBtn() {
    if (!this.els.modelBtn) return;
    const label = this.currentModel
      ? "🧠 " + this.currentModel.displayName
      : "🧠 " + t("chat.noModel");
    this.els.modelBtn.textContent = label;
    this.els.modelBtn.title = t("chat.modelTip");
  },

  openModelPicker() {
    if (!this.models.length) {
      toast(t("chat.noModelHint"), true);
      return;
    }
    const items = this.models.map((m) => ({
      label: m.label, value: m,
      active: this.currentModel &&
        m.providerKey === this.currentModel.providerKey &&
        m.modelName === this.currentModel.modelName,
    }));
    showDropdown(this.els.modelBtn, items, async (it) => {
      this.currentModel = {
        providerKey: it.value.providerKey,
        modelName: it.value.modelName,
        displayName: it.value.displayName,
      };
      this.renderModelBtn();
      await api("chat_select_model", it.value.providerKey,
        it.value.modelName, it.value.displayName);
    });
  },

  renderThinkingToggle() {
    const b = this.els.thinkToggle;
    if (!b) return;
    b.classList.toggle("on", this.thinking);
    b.textContent = "💭 " + t("chat.thinkingMode");
    b.title = t("chat.thinkingTip");
  },

  renderGenerating() {
    if (!this.els.send) return;
    this.els.send.classList.toggle("hidden", this.generating);
    this.els.stop.classList.toggle("hidden", !this.generating);
    this.els.input.disabled = false;
  },

  // ---------------------------------------------------------- 消息渲染
  clearEmpty() {
    const e = this.els.scroll.querySelector(".empty");
    if (e) e.remove();
  },

  renderEmpty() {
    const s = this.els.scroll;
    if (!s) return;
    s.innerHTML = "";
    const empty = el("div", "empty");
    empty.innerHTML = `
      <div class="empty-icon">🐆</div>
      <div class="empty-title">${escapeHtml(t("chat.empty.title"))}</div>
      <div class="empty-sub">${escapeHtml(t("chat.empty.subtitle"))}</div>
      <div class="quick-replies">
        ${[1, 2, 3].map((i) => `<button class="quick-chip" data-q="${escapeHtml(t("chat.quickReply." + i))}">${escapeHtml(t("chat.quickReply." + i))}</button>`).join("")}
      </div>`;
    empty.querySelectorAll(".quick-chip").forEach((chip) => {
      chip.onclick = () => {
        this.els.input.value = chip.dataset.q;
        this.send();
      };
    });
    s.appendChild(empty);
  },

  renderMessages() {
    const s = this.els.scroll;
    s.innerHTML = "";
    this.stream = null;
    if (!this.messages.length) { this.renderEmpty(); return; }
    this.messages.forEach((m) => {
      if (m.role === "user") this.appendUserBubble(m.content);
      else if (m.role === "assistant") this.appendAssistantStatic(m.content);
    });
    this.scrollBottom(true);
  },

  appendUserBubble(text) {
    const row = el("div", "msg-row user");
    row.innerHTML = `
      <div class="msg-avatar user">🙂</div>
      <div class="msg-body"><div class="bubble">${mdLite(text)}</div></div>`;
    this.els.scroll.appendChild(row);
  },

  appendAssistantStatic(text) {
    const row = el("div", "msg-row ai");
    row.innerHTML = `
      <div class="msg-avatar ai">🐆</div>
      <div class="msg-body"><div class="bubble">${mdLite(text)}</div></div>`;
    this.els.scroll.appendChild(row);
  },

  // ---------------------------------------------------------- 流式
  startAssistantBubble() {
    this.clearEmpty();
    const row = el("div", "msg-row ai");
    row.innerHTML = `
      <div class="msg-avatar ai">🐆</div>
      <div class="msg-body">
        <div class="steps hidden"></div>
        <div class="thinking-box hidden">
          <div class="thinking-head"><span class="arrow">▶</span><span>${escapeHtml(t("chat.thinkingProcess"))}</span></div>
          <div class="thinking-content"></div>
        </div>
        <div class="bubble"><span class="answer"></span><span class="typing"><i></i><i></i><i></i></span></div>
        <div class="refs hidden"></div>
      </div>`;
    row.querySelector(".thinking-head").onclick = (e) => {
      e.currentTarget.parentElement.classList.toggle("open");
    };
    this.els.scroll.appendChild(row);
    this.stream = {
      row,
      steps: row.querySelector(".steps"),
      thinkBox: row.querySelector(".thinking-box"),
      thinkContent: row.querySelector(".thinking-content"),
      bubble: row.querySelector(".bubble"),
      answer: row.querySelector(".answer"),
      typing: row.querySelector(".typing"),
      refs: row.querySelector(".refs"),
      answerText: "",
      reasoningText: "",
    };
    this.scrollBottom(true);
  },

  appendReasoning(text) {
    const st = this.stream;
    if (!st) return;
    st.reasoningText += text;
    st.thinkBox.classList.remove("hidden");
    st.thinkContent.textContent = st.reasoningText;
    this.scrollBottom();
  },

  appendAnswer(text) {
    const st = this.stream;
    if (!st) return;
    st.answerText += text;
    if (st.typing) st.typing.remove();
    st.typing = null;
    st.answer.innerHTML = mdLite(st.answerText);
    this.scrollBottom();
  },

  renderSteps(steps) {
    const st = this.stream;
    if (!st || !steps || !steps.length) return;
    st.steps.classList.remove("hidden");
    st.steps.innerHTML = steps.map((s) => {
      const name = t("chat.step." + s.kind) !== ("chat.step." + s.kind)
        ? t("chat.step." + s.kind) : s.kind;
      let detail = "";
      if (s.kind === "search" && s.status === "done" && s.detail !== "") {
        detail = t("chat.step.searchFound", { count: s.detail });
      } else if (s.kind === "search" && s.status === "running" && s.detail) {
        detail = String(s.detail);
      }
      return `<div class="step ${s.status}">
        <div class="step-dot"></div>
        <div><div class="step-name">${escapeHtml(name)}</div>
        ${detail ? `<div class="step-detail">${escapeHtml(detail)}</div>` : ""}</div>
      </div>`;
    }).join("");
    this.scrollBottom();
  },

  appendRefs(refs) {
    const st = this.stream;
    if (!st || !refs || !refs.length) return;
    st.refs.classList.remove("hidden");
    st.refs.innerHTML = `<div class="refs-label">${escapeHtml(t("chat.references"))}</div>` +
      refs.map((r) => {
        const label = r.file_name || r.fileName || r.source || r.chunk_id || "";
        const page = r.page ? ` · ${t("chat.page", { page: r.page })}` : "";
        return `<span class="ref-chip">${escapeHtml(label)}${escapeHtml(page)}</span>`;
      }).join("");
    this.scrollBottom();
  },

  appendError(msg) {
    const st = this.stream;
    if (st) {
      if (st.typing) { st.typing.remove(); st.typing = null; }
      st.answer.innerHTML = `<span class="text-danger">${escapeHtml(msg)}</span>`;
    } else {
      // 无流式气泡（如无模型直接报错）：创建静态错误气泡
      this.clearEmpty();
      const row = el("div", "msg-row ai");
      row.innerHTML = `
        <div class="msg-avatar ai">🐆</div>
        <div class="msg-body"><div class="bubble"><span class="text-danger">${escapeHtml(msg)}</span></div></div>`;
      this.els.scroll.appendChild(row);
      this.scrollBottom(true);
    }
  },

  finishStream() {
    if (this.stream) {
      if (this.stream.answerText) {
        this.messages.push({ role: "assistant", content: this.stream.answerText });
      }
      // 折叠思考过程
      this.stream.thinkBox.classList.remove("open");
      this.stream = null;
    }
  },

  // ---------------------------------------------------------- 发送
  async send() {
    const text = this.els.input.value.trim();
    if (!text || this.generating) return;
    if (!this.currentModel && !this.hasRag) {
      toast(t("chat.noModelNoRag"), true);
      return;
    }
    this.els.input.value = "";
    this.els.input.style.height = "auto";
    const id = await api("chat_send", this.convId, text, this.thinking);
    if (id > 0 && id !== this.convId) {
      this.convId = id;
      this.renderConvList();
    }
  },

  // ---------------------------------------------------------- 滚动
  scrollBottom(force) {
    const s = this.els.scroll;
    if (!s) return;
    const nearBottom = s.scrollHeight - s.scrollTop - s.clientHeight < 120;
    if (force || nearBottom) s.scrollTop = s.scrollHeight;
  },
};

Pages.chat = ChatPage;
