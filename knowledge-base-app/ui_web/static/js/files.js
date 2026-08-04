/* ============================================================
   文件页 — 文档列表 / 导入（原生文件框 + 进度）/ 删除
   ============================================================ */
"use strict";

const FilesPage = {
  docs: [],
  importing: false,
  els: {},

  async init() {
    const root = document.getElementById("page-files");
    root.innerHTML = `
      <div class="page-head">
        <div class="page-title" data-t="files.title"></div>
        <div class="toolbar-spacer"></div>
        <button id="files-refresh" class="btn" data-t="common.refresh"></button>
        <button id="files-import" class="btn btn-primary" data-t="files.import"></button>
      </div>
      <div class="progress hidden" id="files-progress"><i></i></div>
      <div class="page-panel glass panel">
        <div class="scroll-area" id="files-scroll"></div>
      </div>`;
    this.els = {
      importBtn: document.getElementById("files-import"),
      refreshBtn: document.getElementById("files-refresh"),
      progress: document.getElementById("files-progress"),
      bar: document.querySelector("#files-progress > i"),
      scroll: document.getElementById("files-scroll"),
    };
    this.els.importBtn.onclick = () => this.importFiles();
    this.els.refreshBtn.onclick = () => this.load();

    Bus.on("files", "documentsChanged", (docs) => {
      this.docs = docs || [];
      this.render();
    });
    Bus.on("files", "importProgress", (p) => {
      this.els.progress.classList.remove("hidden");
      this.els.bar.style.width = (p.percent || 0) + "%";
      if (p.msg) setStatus(p.msg);
    });
    Bus.on("files", "importRunning", (b) => {
      this.importing = !!b;
      this.els.importBtn.disabled = !!b;
      if (!b) setTimeout(() => { this.els.progress.classList.add("hidden"); this.els.bar.style.width = "0"; }, 600);
    });
    Bus.on("files", "importDone", () => this.load());

    this.refreshTexts();
    await this.load();
  },

  refreshTexts() {
    if (!this.els.importBtn) return;
    document.querySelectorAll("#page-files [data-t]").forEach((e) => {
      e.textContent = t(e.getAttribute("data-t"));
    });
    this.render();
  },
  rerender() { this.refreshTexts(); },
  onShow() { this.load(); },

  async load() {
    this.docs = await api("files_list") || [];
    this.render();
  },

  async importFiles() {
    if (this.importing) return;
    const paths = await api("files_pick");
    if (paths && paths.length) await api("files_import", paths);
  },

  async deleteDoc(doc) {
    const ok = await confirmDialog(t("files.deleteConfirm", { name: doc.fileName }),
      { danger: true, okLabel: t("common.delete") });
    if (ok) await api("files_delete", doc.docId);
  },

  statusBadge(status, statusKey) {
    const map = {
      completed: "badge-success", failed: "badge-danger",
      deleting: "badge-warn", pending: "badge-muted",
    };
    const cls = map[status] || "badge-accent";
    return `<span class="badge ${cls}">${escapeHtml(t(statusKey))}</span>`;
  },

  render() {
    const s = this.els.scroll;
    if (!s) return;
    if (!this.docs.length) {
      s.innerHTML = `<div class="empty"><div class="empty-icon">📁</div>
        <div class="empty-title">${escapeHtml(t("files.empty"))}</div></div>`;
      return;
    }
    const rows = this.docs.map((d) => `
      <tr>
        <td>${escapeHtml(d.fileName)}</td>
        <td>${this.statusBadge(d.status, d.statusKey)}</td>
        <td>${escapeHtml(d.pageCount || "—")}</td>
        <td class="text-right">
          <button class="btn btn-sm btn-danger" data-del="${d.docId}">${escapeHtml(t("common.delete"))}</button>
        </td>
      </tr>`).join("");
    s.innerHTML = `<table class="table">
      <thead><tr>
        <th>${escapeHtml(t("files.col.name"))}</th>
        <th class="col-status">${escapeHtml(t("files.col.status"))}</th>
        <th class="col-num">${escapeHtml(t("files.col.pages"))}</th>
        <th class="col-actions"></th>
      </tr></thead><tbody>${rows}</tbody></table>`;
    s.querySelectorAll("[data-del]").forEach((btn) => {
      btn.onclick = () => {
        const doc = this.docs.find((d) => String(d.docId) === btn.getAttribute("data-del"));
        if (doc) this.deleteDoc(doc);
      };
    });
  },
};

Pages.files = FilesPage;
