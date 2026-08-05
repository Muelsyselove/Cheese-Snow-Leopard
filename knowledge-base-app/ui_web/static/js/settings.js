/* ============================================================
   设置页 — 语言 / 模型配置 / 默认模型 / 数据位置 / 凭据 /
            一键部署 / 依赖管理 / 方案选择 / 计算设备
   ============================================================ */
"use strict";

const SettingsPage = {
  data: null,
  selectedProvider: null,
  depLog: [],
  bootstrapLog: [],
  depRunning: false,
  bootstrapRunning: false,
  migrateRunning: false,
  els: {},

  async init() {
    const root = document.getElementById("page-settings");
    root.innerHTML = `
      <div class="page-head">
        <div class="page-title" data-t="settings.title"></div>
      </div>
      <div class="page-body settings-grid">
        <div class="glass panel" id="sec-language"></div>
        <div class="glass panel" id="sec-appearance"></div>
        <div class="glass panel" id="sec-models"></div>
        <div class="glass panel" id="sec-defaults"></div>
        <div class="glass panel" id="sec-scheme"></div>
        <div class="glass panel" id="sec-compute"></div>
        <div class="glass panel" id="sec-credentials"></div>
        <div class="glass panel" id="sec-deps"></div>
        <div class="glass panel" id="sec-bootstrap"></div>
        <div class="glass panel" id="sec-data"></div>
      </div>`;
    this.els = {
      language: document.getElementById("sec-language"),
      appearance: document.getElementById("sec-appearance"),
      models: document.getElementById("sec-models"),
      defaults: document.getElementById("sec-defaults"),
      scheme: document.getElementById("sec-scheme"),
      compute: document.getElementById("sec-compute"),
      credentials: document.getElementById("sec-credentials"),
      deps: document.getElementById("sec-deps"),
      bootstrap: document.getElementById("sec-bootstrap"),
      data: document.getElementById("sec-data"),
    };
    this.bindEvents();
    // 骨架占位（loadAll 含 GPU 探测等耗时操作，异步填充，不阻塞 boot）
    Object.values(this.els).forEach((sec) => {
      sec.innerHTML = `<div class="hint">${escapeHtml(t("common.loading"))}</div>`;
    });
    this.loadAll();  // 故意不 await
  },

  rerender() { if (this.data) this.renderAll(); },
  onShow() { if (App.ready) this.loadAll(); },

  bindEvents() {
    Bus.on("settings", "testConnectionResult", (p) => {
      const elx = document.getElementById("test-result");
      if (elx) {
        elx.textContent = (p.ok ? "✅ " : "❌ ") + p.msg;
        elx.classList.remove("text-muted", "text-success", "text-danger");
        elx.classList.add(p.ok ? "text-success" : "text-danger");
      }
      toast((p.ok ? t("settings.testSuccess") : t("settings.testFailed")) + ": " + p.msg, !p.ok);
    });
    Bus.on("settings", "depLog", (line) => {
      this.depLog.push(line);
      const box = document.getElementById("dep-log");
      if (box) { box.textContent = this.depLog.join("\n"); box.scrollTop = box.scrollHeight; }
    });
    Bus.on("settings", "depRunning", (b) => {
      this.depRunning = !!b;
      const btns = document.querySelectorAll("#sec-deps .dep-action");
      btns.forEach((x) => (x.disabled = !!b));
    });
    Bus.on("settings", "depFinished", async (p) => {
      toast(p.msg, !p.ok);
      const d = await api("settings_get_dependencies");
      this.data.coreDeps = d.coreDeps;
      this.data.optionalComponents = d.optionalComponents;
      this.renderDeps();
    });
    Bus.on("settings", "depsChanged", async () => {
      if (!this.data) return;
      const d = await api("settings_get_dependencies");
      this.data.coreDeps = d.coreDeps;
      this.data.optionalComponents = d.optionalComponents;
      this.renderDeps();
    });
    Bus.on("settings", "bootstrapLog", (line) => {
      this.bootstrapLog.push(line);
      const box = document.getElementById("bootstrap-log");
      if (box) { box.textContent = this.bootstrapLog.join("\n"); box.scrollTop = box.scrollHeight; }
    });
    Bus.on("settings", "bootstrapRunning", (b) => { this.bootstrapRunning = !!b; });
    Bus.on("settings", "bootstrapFinished", (p) => {
      toast(p.ok ? t("settings.bootstrapDone") : (p.msg || t("common.failed")), !p.ok);
      this.loadAll();
    });
    Bus.on("settings", "migrateRunning", (b) => {
      this.migrateRunning = !!b;
      const btn = document.getElementById("data-change-btn");
      if (btn) btn.disabled = !!b;
    });
    Bus.on("settings", "migrateFinished", (p) => {
      if (p.ok) {
        this.data.dataRoot = p.dataRoot || this.data.dataRoot;
        this.renderData();
        openModal({ title: t("settings.migrateDone"),
          body: escapeHtml(p.msg + t("settings.migrateDoneSuffix")) });
      } else {
        openModal({ title: t("settings.migrateFailed"), body: escapeHtml(p.msg || "") });
      }
    });
    Bus.on("settings", "credentialsChanged", () => this.loadAll());
  },

  async loadAll() {
    this.data = await api("settings_get_all");
    if (this.data && this.data.providers && this.data.providers.length &&
        !this.selectedProvider) {
      this.selectedProvider = this.data.providers[0].key;
    }
    if (this.data) this.renderAll();
  },

  renderAll() {
    if (!this.data) return;
    this.renderLanguage();
    this.renderAppearance();
    this.renderModels();
    this.renderDefaults();
    this.renderScheme();
    this.renderCompute();
    this.renderCredentials();
    this.renderDeps();
    this.renderBootstrap();
    this.renderData();
  },

  // ---------------------------------------------------------- 语言
  renderLanguage() {
    const d = this.data;
    this.els.language.innerHTML = `
      <div class="section-title">${escapeHtml(t("settings.language"))}</div>
      <div class="section-hint">${escapeHtml(t("settings.languageHint"))}</div>
      <div class="form-row">
        <select id="lang-select" class="input">
          ${d.languages.map((l) => `<option value="${l.code}" ${l.code === d.language ? "selected" : ""}>${escapeHtml(l.name)}</option>`).join("")}
        </select>
      </div>`;
    this.els.language.querySelector("#lang-select").onchange = async (e) => {
      await api("i18n_set_language", e.target.value);
    };
  },

  // ---------------------------------------------------------- 外观（画质 + 主题）
  renderAppearance() {
    const qm = window.qualityManager;
    const tm = window.themeManager;
    const q = qm ? qm.getPreference() : "auto";
    const themes = tm ? tm.list() : [];
    const activeId = tm ? tm.active : "dark";
    const cur = themes.find((x) => x.id === activeId);
    const isCustom = !!(cur && !cur.builtin);
    this.els.appearance.innerHTML = `
      <div class="section-title">${escapeHtml(t("settings.appearance"))}</div>
      <div class="section-hint">${escapeHtml(t("settings.appearanceHint"))}</div>
      <div class="form-row">
        <span class="form-label">${escapeHtml(t("settings.quality"))}</span>
        <select id="quality-select" class="input">
          ${["auto", "basic", "high", "ultra"].map((v) =>
            `<option value="${v}" ${v === q ? "selected" : ""}>${escapeHtml(t("settings.quality." + v))}</option>`).join("")}
        </select>
      </div>
      <div class="form-row">
        <span class="form-label">${escapeHtml(t("settings.theme"))}</span>
        <select id="theme-select" class="input">
          ${themes.map((x) =>
            `<option value="${escapeHtml(x.id)}" ${x.id === activeId ? "selected" : ""}>${escapeHtml(x.name)}</option>`).join("")}
        </select>
        <button id="theme-new" class="btn btn-sm">${escapeHtml(t("theme.new"))}</button>
        ${isCustom ? `<button id="theme-edit" class="btn btn-sm">${escapeHtml(t("theme.edit"))}</button>` : ""}
        ${isCustom ? `<button id="theme-del" class="btn btn-sm btn-danger">${escapeHtml(t("common.delete"))}</button>` : ""}
      </div>
      <div class="hint-xs">${escapeHtml(t("settings.themeHint"))}</div>`;
    const sec = this.els.appearance;
    sec.querySelector("#quality-select").onchange = (e) => {
      if (qm) qm.setLevel(e.target.value);
    };
    sec.querySelector("#theme-select").onchange = (e) => {
      if (tm) { tm.apply(e.target.value); this.renderAppearance(); }
    };
    sec.querySelector("#theme-new").onclick = () => this.openThemeEditor(null);
    const editBtn = sec.querySelector("#theme-edit");
    if (editBtn) editBtn.onclick = () => this.openThemeEditor(activeId);
    const delBtn = sec.querySelector("#theme-del");
    if (delBtn) delBtn.onclick = async () => {
      const ok = await confirmDialog(t("theme.deleteConfirm"),
        { danger: true, okLabel: t("common.delete") });
      if (ok && tm) {
        tm.remove(activeId);
        toast(t("theme.deleted"));
        this.renderAppearance();
      }
    };
  },

  // 主题编辑器：新建 / 编辑自定义主题（色板 + 高级 JSON 令牌覆盖）
  openThemeEditor(editId) {
    const tm = window.themeManager;
    if (!tm) return;
    const existing = editId ? tm.get(editId) : null;
    const tokens0 = (existing && existing.tokens) || {};
    const body = el("div");
    const base0 = existing ? (existing.base || "dark") : "light";
    body.innerHTML = `
      <div class="form-row">
        <span class="form-label">${escapeHtml(t("theme.name"))}</span>
        <input id="th-name" class="input form-grow" value="${escapeHtml(existing ? existing.name : "")}"
               placeholder="${escapeHtml(t("theme.namePlaceholder"))}">
      </div>
      <div class="form-row">
        <span class="form-label">${escapeHtml(t("theme.base"))}</span>
        <select id="th-base" class="input">
          <option value="dark" ${base0 === "dark" ? "selected" : ""}>${escapeHtml(t("theme.dark"))}</option>
          <option value="light" ${base0 === "light" ? "selected" : ""}>${escapeHtml(t("theme.light"))}</option>
        </select>
      </div>
      <div class="theme-color-grid">
        ${SettingsPage._themeColorFields.map((f) => `
          <label class="theme-color-item">
            <input type="color" id="thc-${f}" data-token="--${f}">
            <span>${escapeHtml(t("theme.color." + f.replace(/-([a-z])/g, (_, c) => c.toUpperCase())))}</span>
          </label>`).join("")}
      </div>
      <div class="hint-xs mb-s">${escapeHtml(t("theme.advancedHint"))}</div>
      <textarea id="th-adv" class="input theme-adv" spellcheck="false"
        placeholder='{"--glass-fill-top": "rgba(255,255,255,.5)"}'></textarea>`;
    const baseSel = body.querySelector("#th-base");
    const advTa = body.querySelector("#th-adv");
    // 色板回填：编辑时优先用已存令牌，否则用所选基调的内置色板
    const fillColors = (base) => {
      const pal = SettingsPage._themePalettes[base] || SettingsPage._themePalettes.dark;
      SettingsPage._themeColorFields.forEach((f) => {
        const input = body.querySelector(`#thc-${f}`);
        input.value = tokens0["--" + f] || pal[f];
      });
    };
    fillColors(base0);
    // 编辑时：色板之外的高级令牌回填到 JSON 区
    if (existing) {
      const extra = {};
      for (const [k, v] of Object.entries(tokens0)) {
        const key = k.startsWith("--") ? k.slice(2) : k;
        if (!SettingsPage._themeColorFields.includes(key)) extra[k] = v;
      }
      if (Object.keys(extra).length) advTa.value = JSON.stringify(extra, null, 2);
    }
    baseSel.onchange = () => fillColors(baseSel.value);
    openModal({
      title: t(existing ? "theme.edit" : "theme.new"),
      body, wide: true,
      actions: [
        { label: t("common.cancel") },
        {
          label: t("common.save"), primary: true,
          onClick: (close) => {
            const name = body.querySelector("#th-name").value.trim();
            if (!name) { toast(t("theme.nameRequired"), true); return false; }
            const tokens = {};
            SettingsPage._themeColorFields.forEach((f) => {
              tokens["--" + f] = body.querySelector(`#thc-${f}`).value;
            });
            const adv = advTa.value.trim();
            if (adv) {
              try {
                const obj = JSON.parse(adv);
                if (obj && typeof obj === "object") Object.assign(tokens, obj);
              } catch (e) { toast(t("theme.invalidJson"), true); return false; }
            }
            const base = baseSel.value;
            if (existing) {
              tm.update(editId, { name, base, tokens });
              tm.apply(editId);
            } else {
              tm.apply(tm.register({ name, base, tokens }));
            }
            toast(t("theme.saved"));
            this.renderAppearance();
          },
        },
      ],
    });
  },

  // ---------------------------------------------------------- 模型配置
  renderModels() {
    const d = this.data;
    const cur = d.providers.find((p) => p.key === this.selectedProvider) || d.providers[0];
    if (cur) this.selectedProvider = cur.key;
    const listHtml = d.providers.map((p) => `
      <div class="provider-item ${p.key === this.selectedProvider ? "active" : ""}" data-pk="${p.key}">
        <span>${escapeHtml(p.displayName)}</span>
        ${p.configured
          ? `<span class="badge badge-success ml-auto">${escapeHtml(t("common.configured"))}</span>`
          : `<span class="badge badge-muted ml-auto">${escapeHtml(t("common.unconfigured"))}</span>`}
      </div>`).join("");
    let detailHtml = `<div class="text-muted">${escapeHtml(t("settings.selectProviderFirst"))}</div>`;
    if (cur) {
      detailHtml = `
        <div class="form-row">
          <span class="form-label">${escapeHtml(t("settings.apiKey"))}</span>
          <input id="api-key-input" class="input form-grow" type="password"
                 placeholder="${escapeHtml(cur.hasApiKey ? "••••••••（已保存，可覆盖）" : t("settings.apiKeyPlaceholder"))}">
          <button id="api-key-save" class="btn btn-primary">${escapeHtml(t("settings.saveApiKey"))}</button>
          <button id="api-key-clear" class="btn btn-danger">${escapeHtml(t("settings.clearKey"))}</button>
        </div>
        <div class="form-row">
          <span class="form-label">${escapeHtml(t("settings.apiBase"))}</span>
          <span class="hint selectable">${escapeHtml(cur.apiBase)}</span>
          <div class="toolbar-spacer"></div>
          <button id="api-key-apply" class="btn btn-sm">${escapeHtml(t("settings.applyKey"))}</button>
          <button id="api-test" class="btn btn-sm">${escapeHtml(t("settings.testConnection"))}</button>
        </div>
        <div id="test-result"></div>
        <div class="divider"></div>
        <div class="text-sub-m mb-s">${escapeHtml(t("settings.availableModels"))}</div>
        <div class="model-check-list">
          ${cur.models.map((m) => `
            <label class="checkbox">
              <input type="checkbox" data-model="${escapeHtml(m.modelName)}" ${m.enabled ? "checked" : ""}>
              <span class="box"></span>
              <span>${escapeHtml(m.displayName)}</span>
              <span class="hint-xs">${escapeHtml(m.modelName)}</span>
            </label>`).join("")}
        </div>
        <div class="form-row">
          <button id="model-states-save" class="btn">${escapeHtml(t("settings.saveModelStates"))}</button>
        </div>`;
    }
    this.els.models.innerHTML = `
      <div class="section-title">${escapeHtml(t("settings.models"))}</div>
      <div class="section-hint">${escapeHtml(t("settings.modelsHint"))}</div>
      <div class="provider-layout">
        <div class="provider-list">${listHtml}</div>
        <div class="provider-detail">${detailHtml}</div>
      </div>`;
    // 绑定
    this.els.models.querySelectorAll(".provider-item").forEach((item) => {
      item.onclick = () => { this.selectedProvider = item.dataset.pk; this.renderModels(); };
    });
    if (!cur) return;
    const q = (sel) => this.els.models.querySelector(sel);
    q("#api-key-save").onclick = async () => {
      const v = q("#api-key-input").value.trim();
      if (!v) { toast(t("settings.fillApiKey")); return; }
      if (await api("settings_save_api_key", cur.key, v)) {
        q("#api-key-input").value = "";
        await this.refreshProviders();
        ChatPage.models = (await api("chat_reload_models")).models;
      }
    };
    q("#api-key-clear").onclick = async () => {
      const ok = await confirmDialog(t("settings.clearKeyConfirm"), { danger: true });
      if (ok && await api("settings_clear_api_key", cur.key)) {
        await this.refreshProviders();
        ChatPage.models = (await api("chat_reload_models")).models;
      }
    };
    q("#api-key-apply").onclick = () => api("settings_open_key_apply_url", cur.key);
    q("#api-test").onclick = () => {
      const rst = q("#test-result");
      if (rst) {
        rst.textContent = t("settings.testing");
        rst.classList.remove("text-success", "text-danger");
        rst.classList.add("text-muted");
      }
      api("settings_test_connection", cur.key, q("#api-key-input").value.trim());
    };
    q("#model-states-save").onclick = async () => {
      const states = {};
      this.els.models.querySelectorAll("[data-model]").forEach((cb) => {
        states[cb.getAttribute("data-model")] = cb.checked;
      });
      if (await api("settings_save_model_states", cur.key, states)) {
        await this.refreshProviders();
        const st = await api("chat_reload_models");
        ChatPage.models = st.models; ChatPage.currentModel = st.currentModel;
        ChatPage.renderModelBtn();
        this.renderDefaults();
      }
    };
  },

  async refreshProviders() {
    this.data.providers = await api("settings_get_providers");
    this.data.enabledModels = (await api("settings_get_all")).enabledModels;
    this.renderModels();
    this.renderDefaults();
  },

  // ---------------------------------------------------------- 默认模型
  renderDefaults() {
    const d = this.data;
    const opts = (sel) => `
      <option value="">${escapeHtml(t("common.auto"))}</option>
      ${d.enabledModels.map((m) => `
        <option value="${m.providerKey}|${m.modelName}"
          ${sel && sel.providerKey === m.providerKey && sel.modelName === m.modelName ? "selected" : ""}>
          ${escapeHtml(m.label)}</option>`).join("")}`;
    this.els.defaults.innerHTML = `
      <div class="section-title">${escapeHtml(t("settings.defaults"))}</div>
      <div class="section-hint">${escapeHtml(t("settings.defaultsHint"))}</div>
      ${d.defaultRoles.map((r) => `
        <div class="form-row">
          <span class="form-label">${escapeHtml(t(r.roleKey))}</span>
          <select class="input form-grow" data-role="${r.role}">${opts(r)}</select>
        </div>`).join("")}
      <div class="form-row">
        <button id="defaults-save" class="btn btn-primary">${escapeHtml(t("settings.saveDefaults"))}</button>
      </div>`;
    this.els.defaults.querySelector("#defaults-save").onclick = async () => {
      const mapping = {};
      this.els.defaults.querySelectorAll("[data-role]").forEach((sel) => {
        if (sel.value) mapping[sel.getAttribute("data-role")] = sel.value.split("|");
      });
      if (await api("settings_set_default_models", mapping)) {
        const st = await api("chat_reload_models");
        ChatPage.currentModel = st.currentModel;
        ChatPage.renderModelBtn();
      }
    };
  },

  // ---------------------------------------------------------- 方案选择
  renderScheme() {
    const d = this.data;
    const vlmOpts = [["A", t("settings.scheme.vlmA")], ["B", t("settings.scheme.vlmB")], ["C", t("settings.scheme.vlmC")]];
    const embOpts = [["A", t("settings.scheme.embedA")], ["B", t("settings.scheme.embedB")]];
    this.els.scheme.innerHTML = `
      <div class="section-title">${escapeHtml(t("settings.scheme"))}</div>
      <div class="form-row">
        <span class="form-label">${escapeHtml(t("settings.scheme.vlm"))}</span>
        <select id="scheme-vlm" class="input form-grow">
          ${vlmOpts.map(([v, l]) => `<option value="${v}" ${d.scheme.vlm === v ? "selected" : ""}>${escapeHtml(l)}</option>`).join("")}
        </select>
      </div>
      <div class="form-row">
        <span class="form-label">${escapeHtml(t("settings.scheme.embedding"))}</span>
        <select id="scheme-emb" class="input form-grow">
          ${embOpts.map(([v, l]) => `<option value="${v}" ${d.scheme.embedding === v ? "selected" : ""}>${escapeHtml(l)}</option>`).join("")}
        </select>
      </div>
      <div class="form-row">
        <button id="scheme-save" class="btn">${escapeHtml(t("settings.scheme.save"))}</button>
        <span class="hint-xs">${escapeHtml(t("settings.scheme.current", { vlm: d.scheme.vlm, emb: d.scheme.embedding }))}</span>
      </div>`;
    const q = (s) => this.els.scheme.querySelector(s);
    q("#scheme-save").onclick = () =>
      api("settings_save_scheme", q("#scheme-vlm").value, q("#scheme-emb").value);
  },

  // ---------------------------------------------------------- 计算设备
  renderCompute() {
    const d = this.data;
    this.els.compute.innerHTML = `
      <div class="section-title">${escapeHtml(t("settings.compute"))}</div>
      <div class="section-hint">${escapeHtml(t("settings.computeHint"))}</div>
      <div class="form-row">
        <span class="form-label">${escapeHtml(t("settings.compute.device"))}</span>
        <select id="compute-select" class="input form-grow">
          ${d.compute.options.map((o) => `<option value="${o.value}" ${d.compute.device === o.value ? "selected" : ""}>${escapeHtml(o.label)}</option>`).join("")}
        </select>
        <button id="compute-save" class="btn">${escapeHtml(t("common.save"))}</button>
      </div>
      <div class="form-row">
        <span class="hint-xs">${escapeHtml(t("settings.compute.active"))} ${escapeHtml(d.compute.activeDesc)}</span>
      </div>`;
    const q = (s) => this.els.compute.querySelector(s);
    q("#compute-save").onclick = () => api("settings_set_compute_device", q("#compute-select").value);
  },

  // ---------------------------------------------------------- 凭据
  renderCredentials() {
    const d = this.data;
    this.els.credentials.innerHTML = `
      <div class="section-title">${escapeHtml(t("settings.credentials"))}</div>
      <div class="section-hint">${escapeHtml(t("settings.credentialsHint"))}</div>
      ${d.credentials.map((c) => `
        <div class="form-row">
          <span class="form-label" title="${escapeHtml(c.description || "")}">${escapeHtml(c.name)}</span>
          <input class="input form-grow cred-input" type="password" data-cred="${escapeHtml(c.key)}"
                 placeholder="${escapeHtml(c.isSet ? "••••••••（已设置，可覆盖）" : c.placeholder)}">
          <span class="badge ${c.isSet ? "badge-success" : "badge-muted"}">${escapeHtml(c.isSet ? t("common.isSet") : t("common.notSet"))}</span>
        </div>`).join("")}
      <div class="form-row">
        <button id="cred-save" class="btn btn-primary">${escapeHtml(t("settings.saveCredentials"))}</button>
        <button id="cred-clear" class="btn btn-danger">${escapeHtml(t("settings.clearCredentials"))}</button>
      </div>`;
    const q = (s) => this.els.credentials.querySelector(s);
    q("#cred-save").onclick = async () => {
      const values = {};
      this.els.credentials.querySelectorAll(".cred-input").forEach((inp) => {
        if (inp.value.trim()) values[inp.getAttribute("data-cred")] = inp.value.trim();
      });
      if (await api("settings_save_credentials", values)) this.loadAll();
    };
    q("#cred-clear").onclick = async () => {
      const ok = await confirmDialog(t("settings.clearCredentialsConfirm"), { danger: true });
      if (ok) { await api("settings_clear_credentials"); this.loadAll(); }
    };
  },

  // ---------------------------------------------------------- 依赖管理
  renderDeps() {
    const d = this.data;
    this.els.deps.innerHTML = `
      <div class="section-title">${escapeHtml(t("settings.deps"))}</div>
      <div class="hint mb-s">${escapeHtml(t("settings.depsCore"))}</div>
      <div class="form-row gap-s">
        ${d.coreDeps.map((p) => `<span class="badge ${p.installed ? "badge-success" : "badge-danger"}" title="${escapeHtml(p.name)}">${escapeHtml(p.name)}</span>`).join("")}
      </div>
      <div class="divider"></div>
      <div class="hint mb-s">${escapeHtml(t("settings.depsOptional"))}</div>
      <div class="model-check-list">
        ${d.optionalComponents.map((c) => `
          <label class="checkbox">
            <input type="checkbox" data-comp="${c.key}">
            <span class="box"></span>
            <span>${escapeHtml(c.name)}</span>
            <span class="badge ${c.installed ? "badge-success" : "badge-muted"}">${escapeHtml(c.installed ? t("common.installed") : t("common.notInstalled"))}</span>
            <span class="hint-xs">${escapeHtml(c.description)}</span>
          </label>`).join("")}
      </div>
      <div class="form-row">
        <button id="dep-install" class="btn btn-primary dep-action">${escapeHtml(t("settings.installSelected"))}</button>
        <button id="dep-uninstall" class="btn btn-danger dep-action">${escapeHtml(t("settings.uninstallSelected"))}</button>
        <button id="dep-refresh" class="btn">${escapeHtml(t("settings.refreshStatus"))}</button>
      </div>
      <div class="hint mt-s mb-xs">${escapeHtml(t("settings.output"))}</div>
      <div id="dep-log" class="log-box">${escapeHtml(this.depLog.slice(-200).join("\n"))}</div>`;
    const q = (s) => this.els.deps.querySelector(s);
    const selected = () => Array.from(this.els.deps.querySelectorAll("[data-comp]:checked"))
      .map((cb) => cb.getAttribute("data-comp"));
    const runTask = async (install) => {
      const keys = selected();
      if (!keys.length) { toast(t("settings.selectComponentFirst")); return; }
      const names = this.data.optionalComponents
        .filter((c) => keys.includes(c.key)).map((c) => " - " + c.name).join("\n");
      const ok = await confirmDialog(t("settings.installConfirm", {
        action: install ? t("settings.action.install") : t("settings.action.uninstall"),
        names,
      }));
      if (ok) { this.depLog = []; api("settings_run_dependency_task", keys, install); }
    };
    q("#dep-install").onclick = () => runTask(true);
    q("#dep-uninstall").onclick = () => runTask(false);
    q("#dep-refresh").onclick = async () => {
      const dd = await api("settings_get_dependencies");
      this.data.coreDeps = dd.coreDeps;
      this.data.optionalComponents = dd.optionalComponents;
      this.renderDeps();
    };
    const box = q("#dep-log");
    box.scrollTop = box.scrollHeight;
  },

  // ---------------------------------------------------------- 一键部署
  renderBootstrap() {
    this.els.bootstrap.innerHTML = `
      <div class="section-title">${escapeHtml(t("settings.bootstrap"))}</div>
      <div class="section-hint">${escapeHtml(t("settings.bootstrapHint"))}</div>
      <div class="form-row">
        <button id="bootstrap-run" class="btn btn-primary">${escapeHtml(t("settings.bootstrapRun"))}</button>
      </div>`;
    this.els.bootstrap.querySelector("#bootstrap-run").onclick = async () => {
      if (this.bootstrapRunning) { toast(t("settings.bootstrapRunning")); return; }
      const ok = await confirmDialog(t("settings.bootstrapConfirm"));
      if (!ok) return;
      this.bootstrapLog = [];
      const body = el("div");
      body.innerHTML = `
        <div class="hint mb-s">${escapeHtml(t("settings.bootstrapLog"))}</div>
        <div id="bootstrap-log" class="log-box tall"></div>`;
      openModal({ title: t("settings.bootstrapProgressTitle"), body, wide: true });
      api("settings_run_bootstrap");
    };
  },

  // ---------------------------------------------------------- 数据位置
  renderData() {
    const d = this.data;
    this.els.data.innerHTML = `
      <div class="section-title">${escapeHtml(t("settings.dataLocation"))}</div>
      <div class="section-hint">${escapeHtml(t("settings.dataLocationHint"))}</div>
      <div class="form-row">
        <span class="form-label">${escapeHtml(t("settings.currentLocation"))}</span>
        <span class="text-sub selectable break-all">${escapeHtml(d.dataRoot)}</span>
        <button id="data-change-btn" class="btn" ${this.migrateRunning ? "disabled" : ""}>${escapeHtml(t("settings.changeLocation"))}</button>
      </div>`;
    this.els.data.querySelector("#data-change-btn").onclick = async () => {
      const dir = await api("settings_pick_data_directory");
      if (!dir) return;
      const ok = await confirmDialog(t("settings.migrateConfirm", { dir }));
      if (ok) api("settings_migrate_data", dir);
    };
  },
};

Pages.settings = SettingsPage;

// ---------------------------------------------------------- 主题编辑器静态配置
// 色板字段（编辑器中的 color input ↔ 设计令牌映射）
SettingsPage._themeColorFields = [
  "bg-top", "bg-mid", "bg-bottom",
  "blob-cyan", "blob-violet", "blob-pink",
  "accent", "accent-violet", "text-primary",
];
// 内置主题色板（编辑器默认值；与 app.css 中 :root / [data-theme="light"] 对齐）
SettingsPage._themePalettes = {
  dark: {
    "bg-top": "#141B36", "bg-mid": "#0B0F1E", "bg-bottom": "#0F1531",
    "blob-cyan": "#22D3EE", "blob-violet": "#8B5CF6", "blob-pink": "#EC4899",
    "accent": "#22D3EE", "accent-violet": "#A78BFA", "text-primary": "#F2F5FF",
  },
  light: {
    "bg-top": "#FBF7EE", "bg-mid": "#F6F1E5", "bg-bottom": "#EFE8D8",
    "blob-cyan": "#7DD3FC", "blob-violet": "#C4B5FD", "blob-pink": "#F9A8D4",
    "accent": "#0CA5C0", "accent-violet": "#8B7CF6", "text-primary": "#3A382F",
  },
};
