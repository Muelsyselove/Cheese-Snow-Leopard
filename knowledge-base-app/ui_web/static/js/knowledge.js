/* ============================================================
   知识库页 — 分类仪表盘（圆环下钻 / 随机知识卡片）/ 向量库重建 / 清空重置
   ============================================================ */
"use strict";

const KnowledgePage = {
  total: 0,
  tree: [],            // [{id,name,count,children}]
  path: [],            // 当前下钻路径（分类对象数组，path[0] 为一级分类）
  chunks: [],          // 当前随机知识卡片缓存
  rebuilding: false,
  els: {},
  _cardsReq: 0,        // 卡片请求序号（防竞态）

  async init() {
    const root = document.getElementById("page-knowledge");
    root.innerHTML = `
      <div class="page-head">
        <div class="page-title" data-t="knowledge.title"></div>
        <div class="toolbar-spacer"></div>
        <button id="kn-refresh" class="btn" data-t="common.refresh"></button>
        <button id="kn-rebuild" class="btn btn-primary" data-t="knowledge.rebuild"></button>
        <button id="kn-reset" class="btn btn-danger" data-t="knowledge.resetAll"></button>
      </div>
      <div class="progress hidden" id="kn-progress"><i></i></div>
      <div id="kn-progress-msg" class="hint-xs"></div>
      <div class="page-body">
        <div class="kn-dash glass panel" id="kn-dash">
          <div class="kn-main">
            <div class="kn-donut-wrap" id="kn-donut-wrap"></div>
            <div class="kn-detail" id="kn-detail"></div>
          </div>
          <div class="kn-cards-title">
            <span class="kn-cards-label" data-t="knowledge.randomPicks"></span>
            <button id="kn-shuffle" class="btn btn-sm" data-t="knowledge.refreshPicks"></button>
          </div>
          <div class="kn-cards" id="kn-cards"></div>
        </div>
      </div>`;
    this.els = {
      dash: document.getElementById("kn-dash"),
      donutWrap: document.getElementById("kn-donut-wrap"),
      detail: document.getElementById("kn-detail"),
      cards: document.getElementById("kn-cards"),
      rebuild: document.getElementById("kn-rebuild"),
      reset: document.getElementById("kn-reset"),
      refresh: document.getElementById("kn-refresh"),
      shuffle: document.getElementById("kn-shuffle"),
      progress: document.getElementById("kn-progress"),
      bar: document.querySelector("#kn-progress > i"),
      msg: document.getElementById("kn-progress-msg"),
    };
    this.els.refresh.onclick = () => this.load();
    this.els.rebuild.onclick = () => this.rebuild();
    this.els.reset.onclick = () => this.resetAll();
    this.els.shuffle.onclick = () => this.refreshCards();
    // 圆环弧段/图例点击（事件委托，svg 重绘不丢绑定）
    this.els.donutWrap.addEventListener("click", (e) => {
      const seg = e.target && e.target.closest
        ? e.target.closest(".kn-seg, .kn-legend-item") : null;
      if (seg) this.selectTopCategory(seg.getAttribute("data-cat"));
    });

    // 幂等守卫：防止 boot 重复执行导致 Bus 处理器重复注册
    if (!this._eventsBound) {
      this._eventsBound = true;
      Bus.on("knowledge", "categoriesChanged", () => this.load());
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
    }

    this.refreshTexts();
    await this.load();
  },

  refreshTexts() {
    if (!this.els.dash) return;
    document.querySelectorAll("#page-knowledge [data-t]").forEach((e) => {
      e.textContent = t(e.getAttribute("data-t"));
    });
    this.renderDonut();
    this.renderDetail();
    this.renderCards();
  },
  rerender() { this.refreshTexts(); },
  onShow() { this.load(); },

  // ---------------------------------------------------------- 数据加载
  async load() {
    let d = null;
    try { d = await api("knowledge_dashboard"); } catch (e) { d = null; }
    this.total = (d && d.total) || 0;
    this.tree = (d && d.tree) || [];
    // 重新解析当前下钻路径（分类可能已被删除）
    const ids = this.path.map((c) => String(c.id));
    const newPath = [];
    let level = this.tree;
    for (const id of ids) {
      const found = (level || []).find((c) => String(c.id) === id);
      if (!found) break;
      newPath.push(found);
      level = found.children;
    }
    this.path = newPath;
    this.renderDonut();
    this.renderDetail();
    this.refreshCards();
  },

  // ---------------------------------------------------------- 圆环图
  renderDonut() {
    const w = this.els.donutWrap;
    if (!w) return;
    const R = 46, C = 2 * Math.PI * R;
    let acc = 0;
    const segs = this.tree.map((cat, i) => {
      const frac = this.total > 0 ? (cat.count || 0) / this.total : 0;
      const len = frac * C;
      const gap = this.tree.length > 1 ? 1.5 : 0;
      const draw = Math.max(len - gap, 0);
      const seg = `<circle class="kn-seg dc-${(i % 8) + 1}" data-cat="${escapeHtml(String(cat.id))}" ` +
        `cx="60" cy="60" r="${R}" stroke-dasharray="${draw.toFixed(2)} ${(C - draw).toFixed(2)}" ` +
        `stroke-dashoffset="${(-acc).toFixed(2)}"><title>${escapeHtml(cat.name)} (${cat.count || 0})</title></circle>`;
      acc += len;
      return seg;
    }).join("");
    // 图例：颜色点 + 分类名 + 条目数，与弧段同色系、可点击下钻
    const legend = this.tree.map((cat, i) =>
      `<div class="kn-legend-item dc-${(i % 8) + 1}" data-cat="${escapeHtml(String(cat.id))}">` +
      `<span class="kn-legend-dot"></span>` +
      `<span class="kn-legend-name">${escapeHtml(cat.name)}</span>` +
      `<span class="kn-legend-count">${cat.count || 0}</span></div>`).join("");
    w.innerHTML = `
      <div class="kn-donut-stage">
        <svg class="kn-donut" viewBox="0 0 120 120">
          <g transform="rotate(-90 60 60)">
            <circle class="kn-track" cx="60" cy="60" r="${R}"></circle>
            ${segs}
          </g>
        </svg>
        <div class="kn-donut-center">
          <div class="kn-total">${this.total}</div>
          <div class="kn-total-label">${escapeHtml(t("knowledge.totalEntries"))}</div>
        </div>
      </div>
      ${this.tree.length ? `<div class="kn-legend">${legend}</div>` : ""}`;
    this.renderSegSel();
  },

  renderSegSel() {
    const id = this.path.length ? String(this.path[0].id) : null;
    this.els.donutWrap.querySelectorAll(".kn-seg, .kn-legend-item").forEach((s) => {
      s.classList.toggle("sel", id !== null && s.getAttribute("data-cat") === id);
    });
  },

  // ---------------------------------------------------------- 下钻
  selectTopCategory(id) {
    const cat = this.tree.find((c) => String(c.id) === id);
    if (!cat) return;
    // 再次点击已选中的一级分类 → 收起回到全部
    if (this.path.length === 1 && String(this.path[0].id) === id) {
      this.drillTo(-1);
      return;
    }
    this.path = [cat];
    this.renderDetail();
    this.refreshCards();
  },

  drillInto(id) {
    const cur = this.path[this.path.length - 1];
    const child = ((cur && cur.children) || []).find((c) => String(c.id) === id);
    if (!child) return;
    this.path.push(child);
    this.renderDetail();
    this.refreshCards();
  },

  drillTo(depth) {
    this.path = depth < 0 ? [] : this.path.slice(0, depth + 1);
    this.renderDetail();
    this.refreshCards();
  },

  renderDetail() {
    const d = this.els.detail;
    if (!d) return;
    if (!this.path.length) {
      this.els.dash.classList.remove("drilled");
      d.innerHTML = "";
      this.renderSegSel();
      return;
    }
    this.els.dash.classList.add("drilled");
    const cur = this.path[this.path.length - 1];
    const crumbs = [`<span class="kn-crumb" data-depth="-1">${escapeHtml(t("knowledge.overview"))}</span>`]
      .concat(this.path.map((c, i) =>
        `<span class="kn-crumb${i === this.path.length - 1 ? " cur" : ""}" data-depth="${i}">${escapeHtml(c.name)}</span>`));
    const children = cur.children || [];
    const chips = children.length
      ? children.map((c) =>
          `<button class="kn-chip" data-chip="${escapeHtml(String(c.id))}">${escapeHtml(c.name)}` +
          `<span class="kn-chip-count">${c.count || 0}</span></button>`).join("")
      : `<span class="hint">${escapeHtml(t("knowledge.drillEmpty"))}</span>`;
    d.innerHTML = `
      <div class="kn-breadcrumb">${crumbs.join('<span class="kn-crumb-sep">/</span>')}</div>
      <div class="kn-cat-name">${escapeHtml(cur.name)}</div>
      <div class="kn-cat-count">${cur.count || 0} ${escapeHtml(t("knowledge.entries"))}</div>
      <div class="kn-chips">${chips}</div>`;
    d.querySelectorAll(".kn-crumb").forEach((c) => {
      c.onclick = () => this.drillTo(parseInt(c.getAttribute("data-depth"), 10));
    });
    d.querySelectorAll(".kn-chip").forEach((chip) => {
      chip.onclick = () => this.drillInto(chip.getAttribute("data-chip"));
    });
    this.renderSegSel();
  },

  // ---------------------------------------------------------- 随机知识卡片
  async refreshCards() {
    const cur = this.path.length ? this.path[this.path.length - 1] : null;
    const reqId = ++this._cardsReq;
    try {
      const chunks = await api("knowledge_random_chunks", cur ? String(cur.id) : "", 12);
      if (reqId !== this._cardsReq) return; // 已有更新的请求，丢弃过期结果
      this.renderCards(chunks || []);
    } catch (e) { /* 拉取失败保留旧卡片 */ }
  },

  renderCards(chunks) {
    if (chunks) this.chunks = chunks;
    const c = this.els.cards;
    if (!c) return;
    const list = this.chunks || [];
    if (!list.length) {
      c.innerHTML = `<div class="hint">${escapeHtml(t("knowledge.noChunks"))}</div>`;
      return;
    }
    // 3 行分配：index % 3；每行一条自动横向滚动（从左向右）的轨道
    const rows = [[], [], []];
    list.forEach((ch, i) => rows[i % 3].push(ch));
    const durs = [56, 68, 61]; // 各行速度错开，避免机械同步
    c.innerHTML = rows.map((row, ri) => {
      if (!row.length) return "";
      // 卡片高度固定、宽度在 220~340px 内随机（本次渲染内固定）
      const cards = row.map((ch) => ({ ch, w: 220 + Math.floor(Math.random() * 121) }));
      // 半幅轨道需足够宽以铺满容器；内容重复若干组后再整体复制一次，
      // 使轨道 = 两个完全相同的一半，配合 translateX(-50% → 0) 无缝循环
      const halfWidth = cards.reduce((s, x) => s + x.w, 0) + (cards.length - 1) * 8;
      const reps = Math.max(1, Math.ceil(1600 / Math.max(halfWidth, 1)));
      let half = "";
      for (let r = 0; r < reps; r++) half += cards.map((x) => this._cardHtml(x.ch, x.w)).join("");
      return `<div class="kn-card-row"><div class="kn-card-track" style="animation-duration:${durs[ri]}s">` +
        half + half + `</div></div>`;
    }).join("");
  },

  _cardHtml(ch, w) {
    const meta = [escapeHtml(ch.docName || "")];
    if (ch.page) meta.push(escapeHtml(t("chat.page", { page: ch.page })));
    return `<div class="kn-card" style="width:${w}px">` +
      `<div class="kn-card-text">${escapeHtml(ch.content || "")}</div>` +
      `<div class="kn-card-meta">${meta.join(" · ")}</div></div>`;
  },

  // ---------------------------------------------------------- 维护操作
  async rebuild() {
    if (this.rebuilding) return;
    const ok = await confirmDialog(t("knowledge.rebuildConfirm"));
    if (ok) await api("knowledge_rebuild");
  },

  async resetAll() {
    const ok = await confirmDialog(t("knowledge.resetConfirm"),
      { danger: true, okLabel: t("knowledge.resetAll") });
    if (!ok) return;
    try {
      await api("knowledge_reset_all");
      toast(t("knowledge.resetDone"));
      this.path = [];
      await this.load();
    } catch (e) {
      toast(t("knowledge.resetFailed", { msg: (e && e.message) || String(e) }), true);
    }
  },
};

Pages.knowledge = KnowledgePage;
