/* ============================================================
   核心框架 — i18n / 桥接事件总线 / Toast / 模态框 / 路由 / 工具
   ============================================================ */
"use strict";

// ---------------------------------------------------------- 全局状态
const App = {
  lang: "zh_CN",
  dicts: {},
  page: "chat",
  ready: false,
};

// ---------------------------------------------------------- i18n
function t(key, params) {
  let text = (App.dicts[App.lang] || {})[key];
  if (text === undefined) text = (App.dicts["zh_CN"] || {})[key];
  if (text === undefined) return key;
  if (params) {
    for (const k of Object.keys(params)) {
      text = text.replaceAll("{" + k + "}", String(params[k]));
    }
  }
  return text;
}

function applyI18n() {
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    el.textContent = t(el.getAttribute("data-i18n"));
  });
  document.querySelectorAll("[data-i18n-title]").forEach((el) => {
    el.title = t(el.getAttribute("data-i18n-title"));
  });
}

// ---------------------------------------------------------- 桥接
function api(name, ...args) {
  return window.pywebview.api[name](...args);
}

const Bus = {
  map: {},
  on(channel, event, fn) {
    const key = channel + "." + event;
    (this.map[key] = this.map[key] || []).push(fn);
  },
  emit(channel, event, payload) {
    const key = channel + "." + event;
    (this.map[key] || []).forEach((fn) => {
      try { fn(payload); } catch (e) { console.error(key, e); }
    });
  },
};

// Python → JS 事件入口（bridge._emit 调用）
window.__bridgeEvent = function (channel, event, payload) {
  Bus.emit(channel, event, payload);
};

// ---------------------------------------------------------- Toast / 状态栏
let _toastTimer = null;
function toast(msg, isError) {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.classList.toggle("error", !!isError);
  el.classList.add("show");
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => el.classList.remove("show"), 2800);
}
function setStatus(msg) {
  document.getElementById("status-text").textContent = msg || t("status.ready");
}

// ---------------------------------------------------------- DOM 工具
function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined && text !== null) e.textContent = text;
  return e;
}
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}
/* markdown-lite：代码块 / 行内代码 / 加粗，其余按纯文本（保留换行） */
function mdLite(src) {
  let s = escapeHtml(src || "");
  s = s.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) =>
    `<pre><code>${code.replace(/\n$/, "")}</code></pre>`);
  s = s.replace(/`([^`\n]+)`/g, "<code>$1</code>");
  s = s.replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>");
  return s;
}

// ---------------------------------------------------------- 模态对话框
function openModal(opts) {
  const root = document.getElementById("modal-root");
  const backdrop = el("div", "modal-backdrop");
  const modal = el("div", "modal glass" + (opts.wide ? " wide" : ""));
  const title = el("div", "modal-title", opts.title || "");
  const body = el("div", "modal-body");
  if (typeof opts.body === "string") body.innerHTML = opts.body;
  else if (opts.body instanceof Node) body.appendChild(opts.body);
  const actions = el("div", "modal-actions");
  const close = () => backdrop.remove();
  (opts.actions || [{ label: t("common.ok"), primary: true }]).forEach((a) => {
    const btn = el("button", "btn" + (a.primary ? " btn-primary" : "") +
      (a.danger ? " btn-danger" : ""), a.label);
    btn.onclick = () => {
      if (a.onClick) { if (a.onClick(close) === false) return; }
      close();
    };
    actions.appendChild(btn);
  });
  modal.appendChild(title);
  modal.appendChild(body);
  if ((opts.actions || []).length !== 0) modal.appendChild(actions);
  backdrop.appendChild(modal);
  backdrop.addEventListener("mousedown", (e) => {
    if (e.target === backdrop && opts.dismissable !== false) close();
  });
  root.appendChild(backdrop);
  return { close, body, modal };
}

function confirmDialog(message, opts = {}) {
  return new Promise((resolve) => {
    const m = openModal({
      title: opts.title || t("common.confirm"),
      body: escapeHtml(message),
      actions: [
        { label: t("common.cancel"), onClick: () => { resolve(false); } },
        {
          label: opts.okLabel || t("common.confirm"),
          primary: !opts.danger, danger: !!opts.danger,
          onClick: () => { resolve(true); },
        },
      ],
    });
    // 背景关闭视为取消
    m.backdropResolve = resolve;
  });
}

// ---------------------------------------------------------- 下拉浮层
let _openDropdown = null;
function showDropdown(anchor, items, onPick) {
  closeDropdown();
  const dd = el("div", "dropdown glass");
  items.forEach((it) => {
    const item = el("div", "dropdown-item" + (it.active ? " active" : ""), it.label);
    item.onclick = () => { closeDropdown(); onPick(it); };
    dd.appendChild(item);
  });
  document.body.appendChild(dd);
  const r = anchor.getBoundingClientRect();
  const dw = Math.max(dd.offsetWidth, r.width);
  let left = Math.min(r.left, window.innerWidth - dw - 12);
  dd.style.left = left + "px";
  dd.style.top = (r.bottom + 6) + "px";
  _openDropdown = dd;
  setTimeout(() => document.addEventListener("mousedown", _ddOutside), 0);
}
function _ddOutside(e) {
  if (_openDropdown && !_openDropdown.contains(e.target)) closeDropdown();
}
function closeDropdown() {
  if (_openDropdown) { _openDropdown.remove(); _openDropdown = null; }
  document.removeEventListener("mousedown", _ddOutside);
}

// ---------------------------------------------------------- 路由
function switchPage(name) {
  App.page = name;
  document.querySelectorAll(".nav-btn").forEach((b) =>
    b.classList.toggle("active", b.dataset.page === name));
  document.querySelectorAll(".page").forEach((p) =>
    p.classList.toggle("active", p.id === "page-" + name));
  closeDropdown();
  const page = Pages[name];
  if (page && page.onShow) page.onShow();
}

// ---------------------------------------------------------- 页面注册表
const Pages = {};

// ---------------------------------------------------------- 启动
function bindShell() {
  document.getElementById("btn-min").onclick = () => api("window_minimize");
  document.getElementById("btn-max").onclick = () => api("window_toggle_maximize");
  document.getElementById("btn-close").onclick = () => api("window_close");
  document.querySelectorAll(".nav-btn").forEach((b) => {
    b.onclick = () => switchPage(b.dataset.page);
  });
}

async function boot() {
  bindShell();
  await api("js_ready");

  // i18n 初始化
  const st = await api("i18n_get_state");
  App.lang = st.language;
  App.dicts = st.dicts;
  applyI18n();
  setStatus(t("status.ready"));

  // 全局事件
  Bus.on("app", "toast", (p) => toast(p.msg, p.isError));
  Bus.on("app", "status", (msg) => setStatus(msg));
  Bus.on("app", "languageChanged", async () => {
    const s2 = await api("i18n_get_state");
    App.lang = s2.language; App.dicts = s2.dicts;
    applyI18n();
    Object.values(Pages).forEach((p) => p.rerender && p.rerender());
  });

  // 页面初始化
  for (const p of Object.values(Pages)) {
    if (p.init) await p.init();
  }
  switchPage("chat");

  // 启动错误提示
  const errors = await api("app_get_startup_errors");
  if (errors && errors.length) {
    openModal({
      title: t("common.warning"),
      body: escapeHtml(t("app.startupWarning") + "\n\n" + errors.join("\n")),
    });
  }
  App.ready = true;
}

if (window.pywebview) {
  window.addEventListener("pywebviewready", boot);
} else {
  window.addEventListener("pywebviewready", boot);
}
