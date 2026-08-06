/* ============================================================
   主题管理器 — 内置主题（dark/light）+ 自定义主题
   接口与创建指南见 static/THEMES.md
   ============================================================ */
"use strict";

class ThemeManager {
  constructor() {
    this.builtins = [
      { id: "dark", nameKey: "theme.dark" },
      { id: "light", nameKey: "theme.light" },
    ];
    this._storageKey = "custom-themes";     // 自定义主题持久化
    this._prefKey = "theme-preference";     // 当前主题 id
    this._appliedProps = [];                // 自定义主题内联覆盖的令牌名（切换时清除）
    this.active = "dark";
    this.init();
  }

  init() {
    const saved = localStorage.getItem(this._prefKey) || "dark";
    this.apply(saved, { persist: false });
  }

  /** 主题列表：[{id, name, builtin, base?}]，供设置页渲染 */
  list() {
    const bi = this.builtins.map((b) => ({
      id: b.id, builtin: true,
      name: (typeof t === "function" ? t(b.nameKey) : b.id),
    }));
    const cu = this._loadCustoms().map((c) => ({
      id: c.id, name: c.name, builtin: false, base: c.base,
    }));
    return bi.concat(cu);
  }

  /** 应用主题。内置主题只切 data-theme；自定义主题 = 基调 + 令牌内联覆盖 */
  apply(id, opts = {}) {
    const theme = this._find(id);
    if (!theme) return false;
    this._clearInline();
    const base = theme.builtin ? theme.id : (theme.base || "dark");
    document.documentElement.setAttribute("data-theme", base);
    if (!theme.builtin && theme.tokens) {
      for (const [k, v] of Object.entries(theme.tokens)) {
        if (typeof v !== "string" || !v.trim()) continue;
        const prop = k.startsWith("--") ? k : "--" + k;
        document.documentElement.style.setProperty(prop, v.trim());
        this._appliedProps.push(prop);
      }
    }
    this.active = id;
    if (opts.persist !== false) localStorage.setItem(this._prefKey, id);
    this._persistForSplash(theme, base);
    window.dispatchEvent(new CustomEvent("themechange", { detail: { id } }));
    return true;
  }

  /** 持久化主题到后端（data/cache/theme_state.json），供启动 Splash 跟随主题 */
  _persistForSplash(theme, base) {
    try {
      if (!window.pywebview || !window.pywebview.api) return;
      const tokens = theme.builtin ? {} : (theme.tokens || {});
      window.pywebview.api.save_theme_state({ id: theme.id, base, tokens });
    } catch { /* 非致命：桥未就绪时跳过 */ }
  }

  /** 注册自定义主题。tokens: {"--bg-top": "#fff", ...}（键可省略 -- 前缀） */
  register({ name, base, tokens }) {
    const customs = this._loadCustoms();
    const id = "custom-" + Date.now().toString(36) +
      Math.floor(Math.random() * 1296).toString(36);
    customs.push({
      id, name: String(name || id),
      base: base === "light" ? "light" : "dark",
      tokens: tokens || {},
    });
    localStorage.setItem(this._storageKey, JSON.stringify(customs));
    return id;
  }

  /** 更新自定义主题（名称/基调/令牌均可改） */
  update(id, { name, base, tokens }) {
    const customs = this._loadCustoms();
    const c = customs.find((x) => x.id === id);
    if (!c) return false;
    if (name !== undefined) c.name = String(name);
    if (base !== undefined) c.base = base === "light" ? "light" : "dark";
    if (tokens !== undefined) c.tokens = tokens;
    localStorage.setItem(this._storageKey, JSON.stringify(customs));
    if (this.active === id) this.apply(id, { persist: false });
    return true;
  }

  /** 删除自定义主题；若删除的是当前主题则回退 dark */
  remove(id) {
    const customs = this._loadCustoms().filter((c) => c.id !== id);
    localStorage.setItem(this._storageKey, JSON.stringify(customs));
    if (this.active === id) this.apply("dark");
  }

  /** 读取单个主题完整定义（编辑器回填用） */
  get(id) { return this._find(id) || null; }

  // ---------------------------------------------------------- 内部
  _find(id) {
    const b = this.builtins.find((x) => x.id === id);
    if (b) return { id: b.id, builtin: true };
    const c = this._loadCustoms().find((x) => x.id === id);
    return c ? { ...c, builtin: false } : null;
  }

  _loadCustoms() {
    try {
      const arr = JSON.parse(localStorage.getItem(this._storageKey) || "[]");
      return Array.isArray(arr) ? arr : [];
    } catch { return []; }
  }

  _clearInline() {
    const root = document.documentElement;
    this._appliedProps.forEach((p) => root.style.removeProperty(p));
    this._appliedProps = [];
  }
}

// 立即实例化（脚本在 body 末尾加载，尽早应用主题避免闪烁）
window.themeManager = new ThemeManager();
