/* ============================================================
   知识库页 — 分类列表 / 向量库重建（进度反馈）
   ============================================================ */
"use strict";

const KnowledgePage = {
  categories: [],
  rebuilding: false,
  els: {},

  async init() {
    const root = document.getElementById("page-knowledge");
    root.innerHTML = `
      <div class="page-head">
        <div class="page-title" data-t="knowledge.title"></div>
        <div class="toolbar-spacer"></div>
        <button id="kn-refresh" class="btn" data-t="common.refresh"></button>
      </div>
      <div class="page-body">
        <div class="glass panel">
          <div class="section-title" data-t="knowledge.categories"></div>
          <div id="kn-cats"></div>
        </div>
        <div class="glass panel">
          <div class="section-title" data-t="knowledge.maintenance"></div>
          <div class="section-hint" data-t="knowledge.maintenanceHint"></div>
          <div class="form-row">
            <button id="kn-rebuild" class="btn btn-primary" data-t="knowledge.rebuild"></button>
          </div>
          <div class="progress hidden" id="kn-progress"><i></i></div>
          <div id="kn-progress-msg" class="hint-xs mt-s"></div>
        </div>
      </div>`;
    this.els = {
      cats: document.getElementById("kn-cats"),
      rebuild: document.getElementById("kn-rebuild"),
      refresh: document.getElementById("kn-refresh"),
      progress: document.getElementById("kn-progress"),
      bar: document.querySelector("#kn-progress > i"),
      msg: document.getElementById("kn-progress-msg"),
    };
    this.els.refresh.onclick = () => this.load();
    this.els.rebuild.onclick = () => this.rebuild();

    Bus.on("knowledge", "categoriesChanged", (cats) => {
      this.categories = cats || [];
      this.renderCats();
    });
    Bus.on("knowledge", "rebuildProgress", (p) => {
      this.els.progress.classList.remove("hidden");
      this.els.bar.style.width = (p.percent || 0) + "%";
      this.els.msg.textContent = p.msg || "";
    });
    Bus.on("knowledge", "rebuilding", (b) => {
      this.rebuilding = !!b;
      this.els.rebuild.disabled = !!b;
      if (!b) setTimeout(() => {
        this.els.progress.classList.add("hidden");
        this.els.bar.style.width = "0";
      }, 800);
    });
    Bus.on("knowledge", "rebuildFinished", (ok) => {
      toast(ok ? t("knowledge.rebuildDone") : t("knowledge.rebuildFailed"), !ok);
      this.load();
    });

    this.refreshTexts();
    await this.load();
  },

  refreshTexts() {
    if (!this.els.rebuild) return;
    document.querySelectorAll("#page-knowledge [data-t]").forEach((e) => {
      e.textContent = t(e.getAttribute("data-t"));
    });
    this.renderCats();
  },
  rerender() { this.refreshTexts(); },
  onShow() { this.load(); },

  async load() {
    this.categories = await api("knowledge_list") || [];
    this.renderCats();
  },

  async rebuild() {
    if (this.rebuilding) return;
    const ok = await confirmDialog(t("knowledge.rebuildConfirm"));
    if (ok) await api("knowledge_rebuild");
  },

  renderCats() {
    const c = this.els.cats;
    if (!c) return;
    if (!this.categories.length) {
      c.innerHTML = `<div class="empty empty-pad">
        <div class="empty-title">${escapeHtml(t("knowledge.empty"))}</div></div>`;
      return;
    }
    const rows = this.categories.map((cat) => `
      <tr><td>${escapeHtml(cat.name)}</td>
      <td class="col-badge"><span class="badge badge-accent">${cat.chunkCount}</span></td></tr>`).join("");
    c.innerHTML = `<table class="table"><thead><tr>
      <th>${escapeHtml(t("knowledge.col.category"))}</th>
      <th>${escapeHtml(t("knowledge.col.chunks"))}</th>
      </tr></thead><tbody>${rows}</tbody></table>`;
  },
};

Pages.knowledge = KnowledgePage;
