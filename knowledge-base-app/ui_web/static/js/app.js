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
/* Markdown 渲染：先整体转义，再按 代码→行内→块级 规则替换（纯手写，无外部依赖） */
function renderMarkdown(src) {
  let s = escapeHtml(src === undefined || src === null ? "" : String(src));

  // 1) 代码块 / 行内代码先提取为占位符，避免内部字符被后续规则误处理
  const codeBlocks = [];
  s = s.replace(/```(\w*)[^\S\n]*\n?([\s\S]*?)```/g, (_, lang, code) => {
    codeBlocks.push({ lang, code: code.replace(/\n$/, "") });
    return "\n\u0000CB" + (codeBlocks.length - 1) + "\u0000\n";
  });
  const inlineCodes = [];
  s = s.replace(/`([^`\n]+)`/g, (_, code) => {
    inlineCodes.push(code);
    return "\u0000IC" + (inlineCodes.length - 1) + "\u0000";
  });

  // 2) 行内样式：链接 / 加粗 / 删除线 / 斜体
  const inline = (txt) => txt
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g,
      '<a class="md-link" data-url="$2">$1</a>')
    .replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>")
    .replace(/__([^_]+)__/g, "<b>$1</b>")
    .replace(/~~([^~]+)~~/g, "<s>$1</s>")
    .replace(/\*([^*\n]+)\*/g, "<i>$1</i>");

  // 3) 块级：表格 / 标题 / 引用 / 列表，逐行聚合
  const isTableRow = (ln) => /^\s*\|.*\|\s*$/.test(ln);
  const isTableSep = (ln) => ln.indexOf("-") !== -1 && /^\s*\|?[\s:|-]+\|?\s*$/.test(ln);
  const parseRow = (ln) => ln.trim().replace(/^\|/, "").replace(/\|$/, "")
    .split("|").map((c) => inline(c.trim()));
  const lines = s.split("\n");
  const out = [];
  let i = 0;
  while (i < lines.length) {
    const ln = lines[i];
    const trimmed = ln.trim();
    // 代码块占位符整行：原样保留
    if (/^\u0000CB\d+\u0000$/.test(trimmed)) { out.push(trimmed); i++; continue; }
    // 表格：当前行 + 紧随的分隔行
    if (isTableRow(ln) && i + 1 < lines.length && isTableSep(lines[i + 1])) {
      const head = parseRow(ln);
      i += 2; // 跳过分隔行
      const bodyRows = [];
      while (i < lines.length && isTableRow(lines[i])) { bodyRows.push(parseRow(lines[i])); i++; }
      out.push(`<table class="md-table"><thead><tr>${head.map((c) => `<th>${c}</th>`).join("")}</tr></thead>` +
        `<tbody>${bodyRows.map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join("")}</tr>`).join("")}</tbody></table>`);
      continue;
    }
    const hm = ln.match(/^\s*(#{1,4})\s+(.+)$/);
    if (hm) { out.push(`<div class="md-h${hm[1].length}">${inline(hm[2])}</div>`); i++; continue; }
    const qm = ln.match(/^\s*>\s?(.*)$/);
    if (qm) { out.push(`<div class="md-quote">${inline(qm[1])}</div>`); i++; continue; }
    if (/^\s*[-*]\s+/.test(ln)) {
      const items = [];
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*[-*]\s+/, "")); i++;
      }
      out.push(`<ul class="md-ul">${items.map((x) => `<li>${inline(x)}</li>`).join("")}</ul>`);
      continue;
    }
    if (/^\s*\d+\.\s+/.test(ln)) {
      const items = [];
      while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*\d+\.\s+/, "")); i++;
      }
      out.push(`<ol class="md-ol">${items.map((x) => `<li>${inline(x)}</li>`).join("")}</ol>`);
      continue;
    }
    out.push(inline(ln));
    i++;
  }
  s = out.join("\n");

  // 4) 还原代码占位符；清理块级元素相邻的多余换行（气泡为 pre-wrap，避免空行）
  s = s.replace(/\u0000CB(\d+)\u0000/g, (_, n) => {
    const b = codeBlocks[+n];
    const langAttr = b.lang ? ` data-lang="${b.lang}"` : "";
    return `<pre class="md-pre"${langAttr}><code>${b.code}</code></pre>`;
  });
  s = s.replace(/\u0000IC(\d+)\u0000/g, (_, n) => `<code class="md-code">${inlineCodes[+n]}</code>`);
  s = s.replace(/\n(?=<(?:div|ul|ol|table|pre)[\s>])/g, "");
  s = s.replace(/(<\/(?:div|ul|ol|table|pre)>)\n/g, "$1");
  return s;
}

// Markdown 链接点击 → 外部浏览器打开（事件委托，全局仅注册一次）
document.addEventListener("click", (e) => {
  const a = e.target && e.target.closest ? e.target.closest(".md-link") : null;
  if (!a) return;
  e.preventDefault();
  const url = a.getAttribute("data-url");
  if (url && window.pywebview && window.pywebview.api) {
    try { api("open_external", url); } catch (err) { console.error("open_external", err); }
  }
});

// ---------------------------------------------------------- 模态对话框
function openModal(opts) {
  const root = document.getElementById("modal-root");
  const backdrop = el("div", "modal-backdrop");
  const modal = el("div", "modal glass" + (opts.wide ? " wide" : ""));
  const title = el("div", "modal-title", opts.title || "");
  const head = el("div", "modal-head");
  const body = el("div", "modal-body");
  if (typeof opts.body === "string") body.innerHTML = opts.body;
  else if (opts.body instanceof Node) body.appendChild(opts.body);
  const actions = el("div", "modal-actions");
  const close = () => backdrop.remove();
  // 标题右上角关闭按钮（除不可关闭的审批弹窗外总显示）
  if (opts.dismissable !== false) {
    const closeBtn = el("button", "modal-close", "✕");
    closeBtn.setAttribute("aria-label", t("common.close"));
    closeBtn.onclick = () => close();
    head.appendChild(title);
    head.appendChild(closeBtn);
  } else {
    head.appendChild(title);
  }
  (opts.actions || [{ label: t("common.ok"), primary: true }]).forEach((a) => {
    const btn = el("button", "btn" + (a.primary ? " btn-primary" : "") +
      (a.danger ? " btn-danger" : ""), a.label);
    btn.onclick = () => {
      if (a.onClick) { if (a.onClick(close) === false) return; }
      close();
    };
    actions.appendChild(btn);
  });
  modal.appendChild(head);
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

// ---------------------------------------------------------- 分类审批弹窗
// 后端在导入文件 AI 分类时推送 files.categoryApproval；多请求可并存多个 modal
function showCategoryApproval(p) {
  if (!p || !p.requestId) return;
  const resolve = (action, extra) => {
    try {
      if (extra === undefined) api("files_resolve_category", p.requestId, action);
      else api("files_resolve_category", p.requestId, action, extra);
    } catch (e) { console.error("files_resolve_category", e); }
  };
  const body = el("div");
  const m = openModal({
    title: t("approve.title"),
    body,
    dismissable: false,
    actions: [
      { label: t("approve.allow"), primary: true, onClick: () => resolve("allow") },
      { label: t("approve.choose"), onClick: () => { renderChoose(); return false; } },
      { label: t("approve.custom"), onClick: () => { renderCustom(); return false; } },
      { label: t("approve.other"), onClick: () => resolve("other") },
    ],
  });
  const renderMain = () => {
    body.innerHTML = `
      <div class="mb-s"><span class="text-sub">${escapeHtml(t("approve.suggested"))}：</span>${escapeHtml((p.suggestedPath || []).join(" / "))}</div>
      <div class="mb-s"><span class="text-sub">${escapeHtml(t("approve.fromDoc"))}：</span>${escapeHtml(p.docName || "")}</div>
      <div class="mb-xs text-sub">${escapeHtml(t("approve.content"))}：</div>
      <div class="log-box">${escapeHtml(String(p.preview || "").slice(0, 200))}</div>`;
  };
  const renderChoose = () => {
    const tree = Array.isArray(p.tree) ? p.tree : [];
    body.innerHTML = `
      <div class="mb-s text-sub">${escapeHtml(t("approve.choose"))}</div>
      <div class="form-row">
        <select class="input form-grow" id="ap-sel">
          ${tree.map((path, i) => `<option value="${i}">${escapeHtml((path || []).join(" / "))}</option>`).join("")}
        </select>
        <button class="btn btn-primary" id="ap-ok">${escapeHtml(t("approve.confirm"))}</button>
      </div>`;
    body.querySelector("#ap-ok").onclick = () => {
      const idx = parseInt(body.querySelector("#ap-sel").value || "0", 10);
      resolve("choose", tree[idx] || []);
      m.close();
    };
  };
  const renderCustom = () => {
    body.innerHTML = `
      <div class="mb-s text-sub">${escapeHtml(t("approve.custom"))}</div>
      <div class="form-row">
        <input class="input form-grow" id="ap-input" placeholder="${escapeHtml(t("approve.customPlaceholder"))}">
        <button class="btn btn-primary" id="ap-ok">${escapeHtml(t("approve.confirm"))}</button>
      </div>`;
    const submit = () => {
      const v = body.querySelector("#ap-input").value.trim();
      if (!v) return;
      const arr = v.split("/").map((x) => x.trim()).filter(Boolean);
      if (!arr.length) return;
      resolve("custom", arr);
      m.close();
    };
    body.querySelector("#ap-ok").onclick = submit;
    body.querySelector("#ap-input").addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.isComposing) submit();
    });
  };
  renderMain();
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

// 从鼠标或触控事件中提取屏幕坐标
function getScreenPos(e) {
  if (e.touches && e.touches.length > 0) {
    return { x: e.touches[0].screenX, y: e.touches[0].screenY };
  }
  if (e.changedTouches && e.changedTouches.length > 0) {
    return { x: e.changedTouches[0].screenX, y: e.changedTouches[0].screenY };
  }
  return { x: e.screenX, y: e.screenY };
}

// 无边框窗口：拖动标题栏移动窗口（pywebview easy_drag=False，改用桥接实现）
// 同时支持鼠标和触控事件。改用"绝对定位 + requestAnimationFrame 节流"，
// 每次移动直接把窗口对准光标位置，避免逐帧异步增量带来的滞后与漂移。
function initWindowDrag() {
  const titlebar = document.getElementById("titlebar");
  const drag = { active: false, sx: 0, sy: 0, offset: null, mx: 0, my: 0, raf: 0 };

  function onDown(e) {
    if (e.button !== undefined && e.button !== 0) return;
    if (e.target.closest(".tb-btn")) return; // 让最小化/最大化/关闭按钮正常点击
    const pos = getScreenPos(e);
    drag.active = true;
    drag.sx = pos.x;
    drag.sy = pos.y;
    drag.offset = null;
    e.preventDefault();
  }

  function onMove(e) {
    if (!drag.active) return;
    const pos = getScreenPos(e);
    drag.mx = pos.x;
    drag.my = pos.y;
    if (!drag.raf) drag.raf = requestAnimationFrame(step);
    e.preventDefault();
  }

  function step() {
    drag.raf = 0;
    if (!drag.active) return;
    if (!drag.offset) {
      // 首次移动：先取窗口当前位置，计算按住点相对窗口的偏移
      api("window_get_bounds").then((b) => {
        if (!drag.active || !b) return;
        drag.offset = { x: drag.sx - b.x, y: drag.sy - b.y };
        doMove();
      });
      return;
    }
    doMove();
  }

  function doMove() {
    api("window_move_abs", drag.mx - drag.offset.x, drag.my - drag.offset.y);
  }

  function onUp() {
    drag.active = false;
    if (drag.raf) { cancelAnimationFrame(drag.raf); drag.raf = 0; }
  }

  titlebar.addEventListener("mousedown", onDown);
  titlebar.addEventListener("touchstart", onDown, { passive: false });
  window.addEventListener("mousemove", onMove);
  window.addEventListener("touchmove", onMove, { passive: false });
  window.addEventListener("mouseup", onUp);
  window.addEventListener("touchend", onUp);
}

// 无边框窗口：边缘/角落拖动缩放（pywebview 无原生缩放，需桥接实现）
// 同时支持鼠标和触控事件。以按下时边界 + 累计位移计算目标矩形，rAF 节流。
function initWindowResize() {
  const drag = { active: false, dir: null, sx: 0, sy: 0, bounds: null, mx: 0, my: 0, raf: 0 };

  function onDown(e) {
    const h = e.currentTarget;
    e.preventDefault();
    const pos = getScreenPos(e);
    drag.active = true;
    drag.dir = h.dataset.dir;
    drag.sx = pos.x;
    drag.sy = pos.y;
    drag.bounds = null;
    document.body.classList.add("win-resizing");
  }

  function onMove(e) {
    if (!drag.active) return;
    const pos = getScreenPos(e);
    drag.mx = pos.x;
    drag.my = pos.y;
    if (!drag.raf) drag.raf = requestAnimationFrame(step);
    e.preventDefault();
  }

  function step() {
    drag.raf = 0;
    if (!drag.active) return;
    if (!drag.bounds) {
      api("window_get_bounds").then((b) => {
        if (!drag.active || !b) return;
        drag.bounds = b;
        doResize();
      });
      return;
    }
    doResize();
  }

  function doResize() {
    const dx = drag.mx - drag.sx;
    const dy = drag.my - drag.sy;
    api("window_resize_abs", drag.dir,
      drag.bounds.x, drag.bounds.y, drag.bounds.width, drag.bounds.height,
      dx, dy);
  }

  function onUp() {
    if (!drag.active) return;
    drag.active = false;
    if (drag.raf) { cancelAnimationFrame(drag.raf); drag.raf = 0; }
    document.body.classList.remove("win-resizing");
  }

  document.querySelectorAll(".rs-handle").forEach((h) => {
    h.addEventListener("mousedown", onDown);
    h.addEventListener("touchstart", onDown, { passive: false });
  });
  window.addEventListener("mousemove", onMove);
  window.addEventListener("touchmove", onMove, { passive: false });
  window.addEventListener("mouseup", onUp);
  window.addEventListener("touchend", onUp);
}

async function boot() {
  // 幂等守卫：tryBoot 会被脚本加载 / pywebviewready / 轮询多处触发，仅允许执行一次
  if (App._booted) return;
  App._booted = true;
  try {
    bindShell();
    // 效果分级初始化（在页面渲染前确定画质）
    window.qualityManager = new QualityManager();
    initWindowDrag();
    initWindowResize();

    // 窗口失焦/最小化时暂停背景动画
    document.addEventListener('visibilitychange', () => {
      const aurora = document.querySelector('.aurora');
      if (!aurora) return;
      if (document.hidden) {
        aurora.style.animationPlayState = 'paused';
      } else {
        aurora.style.animationPlayState = '';
      }
    });

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
    // 分类审批（知识库管家）— 仅注册一次
    if (!App._approvalBound) {
      App._approvalBound = true;
      Bus.on("files", "categoryApproval", (p) => showCategoryApproval(p));
    }
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
  } catch (e) {
    console.error("boot 初始化失败:", e);
  }
}

// ---------------------------------------------------------- 启动（带轮询兜底）
// pywebview 在 NavigationCompleted 后通过 inject_pywebview 注入 API，
// 但 finish.js 在后台线程执行，pywebviewready 可能延迟或异常未触发。
// 因此采用"事件 + 轮询"双重保障。
function tryBoot() {
  // 仅在 api 桥接方法就绪后再调用 boot，避免 await api("js_ready") 挂起
  if (window.pywebview && window.pywebview.api
      && typeof window.pywebview.api.js_ready === 'function') {
    boot();
    return true;
  }
  return false;
}

function bootFallback() {
  if (!tryBoot()) {
    setTimeout(tryBoot, 100); // 每 100ms 轮询一次
  }
}

// 首次尝试：脚本加载时 pywebview 可能已就绪
if (!tryBoot()) {
  // 未就绪：pywebviewready 事件 + 轮询
  window.addEventListener("pywebviewready", bootFallback);
  // DOMContentLoaded 后开始轮询（兜底）
  document.addEventListener("DOMContentLoaded", () => {
    if (!tryBoot()) {
      setTimeout(function poll() {
        if (!tryBoot()) setTimeout(poll, 100);
      }, 100);
    }
  });
}
