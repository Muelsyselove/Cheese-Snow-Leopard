# UI 组件使用说明

> 知识学爆 Cheese Snow Leopard — Web UI 液态玻璃主题
>
> 设计原则：**所有样式集中管理，杜绝硬编码**。前端 JS 只负责结构拼接与行为，视觉表现全部交由 CSS 类控制。

---

## 目录

1. [设计令牌 (Design Tokens)](#1-设计令牌-design-tokens)
2. [布局骨架](#2-布局骨架)
3. [基础组件](#3-基础组件)
4. [表单与输入](#4-表单与输入)
5. [状态与反馈](#5-状态与反馈)
6. [文字变体（语义化颜色/字号）](#6-文字变体)
7. [间距工具](#7-间距工具)
8. [表格列宽](#8-表格列宽)
9. [对话页专属组件](#9-对话页专属组件)
10. [页面组装示例](#10-页面组装示例)
11. [效果分级系统](#11-效果分级系统)
12. [知识库仪表盘组件](#12-知识库仪表盘组件)

---

## 1. 设计令牌 (Design Tokens)

全部定义于 `app.css :root`，任何组件不得再写死色值/尺寸。主要分类：

| 类别 | 示例变量 | 用途 |
|------|---------|------|
| 背景 | `--bg-top`, `--bg-mid`, `--bg-bottom` | 页面渐变底色 |
| 文字 | `--text-primary`, `--text-secondary`, `--text-muted` | 三级文字色 |
| 强调色 | `--accent`, `--accent-violet`, `--danger`, `--success`, `--warning` | 主操作/危险/成功/警告 |
| 玻璃材质 | `--glass-fill-top`, `--glass-border-top`, `--glass-inner-shadow` | `.glass` 组件材质 |
| 圆角 | `--r-s`, `--r-m`, `--r-l`, `--r-xl` | 小/中/大/超大圆角 |
| 间距 | `--sp-xs` ~ `--sp-xxl` | 4px / 8px / 12px / 16px / 24px / 32px |
| 字号 | `--fs-xs` ~ `--fs-title` | 10px / 12px / 14px / 17px / 22px / 26px |
| 动效 | `--anim-fast`, `--anim-med`, `--anim-slow` | 120ms / 220ms / 420ms |

> 改主题只需改 `:root`，组件自动跟随。

---

## 2. 布局骨架

```html
<!-- 顶层 -->
<div id="app">
  <header id="titlebar">…</header>
  <div id="main">
    <nav id="navrail" class="glass">…</nav>
    <main id="pages">
      <section id="page-xxx" class="page active">…</section>
    </main>
  </div>
  <footer id="statusbar" class="glass">…</footer>
</div>
```

| 类/ID | 说明 |
|-------|------|
| `#app` | 根容器，flex column，带 10px 外衬 |
| `#titlebar` | 标题栏（frameless 自绘），高 `--tb-h` |
| `#main` | 主内容区，flex row |
| `#navrail` | 左侧导航，宽 `--nav-w`，`.glass` 材质 |
| `#pages` | 页面栈，相对定位，各 `.page` absolute 叠放 |
| `.page` | 单页，默认 `display:none`；`.active` 切为 flex column |
| `#statusbar` | 状态栏，高 `--sb-h` |
| `.page-head` | 页头：标题 + 工具按钮行 |
| `.page-title` | 页面大标题，字号 `--fs-xl` |
| `.page-body` | 可滚动内容区，flex column |
| `.page-panel` | 内容面板，flex column，占满剩余空间 |
| `.scroll-area` | 滚动容器，`overflow-y:auto` |
| `.settings-grid` | 设置页纵向排列的面板组 |

---

## 3. 基础组件

### 3.1 玻璃面板 `.glass`
> 液态玻璃核心材质。带折射描边 + 顶部高光。

```html
<div class="glass">内容</div>
<div class="glass panel">带内边距的内容</div>
```

### 3.2 按钮 `.btn`
| 变体 | 类名 | 用途 |
|------|------|------|
| 默认 | `.btn` | 次要操作 |
| 主操作 | `.btn.btn-primary` | 保存、发送、确认 |
| 危险 | `.btn.btn-danger` | 删除、清除 |
| 小尺寸 | `.btn.btn-sm` | 行内紧凑按钮 |
| 图标按钮 | `.btn.btn-icon` | 仅图标 |

```html
<button class="btn btn-primary">保存</button>
<button class="btn btn-sm">小按钮</button>
```

### 3.3 徽章 `.badge`
| 变体 | 类名 |
|------|------|
| 成功 | `.badge.badge-success` |
| 灰色 | `.badge.badge-muted` |
| 警告 | `.badge.badge-warn` |
| 危险 | `.badge.badge-danger` |
| 强调 | `.badge.badge-accent` |

```html
<span class="badge badge-success">已配置</span>
```

### 3.4 进度条 `.progress`
```html
<div class="progress"><i></i></div>
<!-- 隐藏时用 .hidden -->
<div class="progress hidden"><i></i></div>
```
> JS 通过 `querySelector('.progress > i').style.width = 'xx%'` 控制进度。

### 3.5 开关 `.switch`
```html
<div class="switch on"></div>
```
> 通过 `.on` 类切换开关状态。

### 3.6 复选框 `.checkbox`
```html
<label class="checkbox">
  <input type="checkbox" checked>
  <span class="box"></span>
  <span>文案</span>
</label>
```

---

## 4. 表单与输入

### 4.1 输入框 `.input`
```html
<input class="input" placeholder="提示">
<textarea class="input" rows="3"></textarea>
<select class="input"><option>…</option></select>
```

### 4.2 表单行 `.form-row`
> 一行内 label + 输入 + 按钮的水平排列。

```html
<div class="form-row">
  <span class="form-label">标签</span>
  <input class="input form-grow">
  <button class="btn">操作</button>
</div>
```

| 辅助类 | 说明 |
|--------|------|
| `.form-label` | 固定宽 110px 的标签 |
| `.form-grow` | 自动撑满剩余宽度 |
| `.gap-s` | 缩小行内 gap 为 8px（可与 `.form-row` 同用） |

### 4.3 方案切换胶囊 `.pill-toggle`
```html
<div class="pill-toggle on">联网搜索</div>
```

---

## 5. 状态与反馈

### 5.1 隐藏 `.hidden`
```html
<div class="progress hidden">…</div>
```
> JS 用 `classList.add/remove('hidden')` 控制显隐，**禁止**写 `style.display`。

### 5.2 文字对齐 / 选择 / 截断
| 类名 | 效果 |
|------|------|
| `.text-right` | 右对齐 |
| `.ml-auto` | `margin-left:auto`，把元素推到右侧 |
| `.selectable` | `user-select:text`，允许文本选中 |
| `.break-all` | `word-break:break-all`，长路径换行 |

### 5.3 Toast `#toast`
```js
toast("保存成功");        // 普通提示
toast("出错了", true);    // 错误提示（红色）
```

### 5.4 模态框 `openModal()`
```js
openModal({
  title: "标题",
  body: "<p>HTML 内容</p>",   // 或 Node
  wide: true,                  // 宽版弹窗
  actions: [
    { label: "取消" },
    { label: "确定", primary: true, onClick: (close) => { close(); } }
  ]
});
```

---

## 6. 文字变体

> 语义化替代零散的内联 `color`/`font-size`。

| 类名 | 字号 | 颜色 |
|------|------|------|
| `.hint` | `--fs-s` | `--text-muted` |
| `.hint-xs` | `--fs-xs` | `--text-muted` |
| `.text-sub` | `--fs-s` | `--text-secondary` |
| `.text-sub-m` | `--fs-m` | `--text-secondary` |
| `.text-muted` | 继承 | `--text-muted` |
| `.text-danger` | 继承 | `--danger` |
| `.text-success` | 继承 | `--success` |

```html
<div class="hint">灰色小字提示</div>
<div class="text-danger">错误信息</div>
```

---

## 7. 间距工具

| 类名 | 效果 |
|------|------|
| `.mb-xs` | `margin-bottom: 4px` |
| `.mb-s` | `margin-bottom: 8px` |
| `.mb-m` | `margin-bottom: 12px` |
| `.mt-xs` | `margin-top: 4px` |
| `.mt-s` | `margin-top: 8px` |
| `.gap-s` | `gap: 8px` |

```html
<div class="hint mb-s">带下边距的提示</div>
<div class="form-row gap-s">缩小间距的行</div>
```

---

## 8. 表格列宽

表格列宽统一在 CSS 中语义化管理，JS 写 `<th class="col-xxx">` 即可。

| 类名 | 宽度 |
|------|------|
| `.table .col-status` | 120px |
| `.table .col-num` | 80px |
| `.table .col-actions` | 90px |
| `.table .col-badge` | 120px |

```html
<table class="table">
  <thead><tr>
    <th>名称</th>
    <th class="col-status">状态</th>
    <th class="col-num">页数</th>
    <th class="col-actions"></th>
  </tr></thead>
</table>
```

---

## 9. 对话页专属组件

| 类名 | 说明 |
|------|------|
| `.chat-sidebar` | 左侧会话列表 |
| `.chat-main` | 右侧消息区 |
| `.msg-row` | 单条消息行（AI `.ai` / 用户 `.user`） |
| `.msg-avatar` | 头像圆片 |
| `.bubble` | 消息气泡 |
| `.thinking-box` | 思考过程折叠面板 |
| `.steps` | 步骤时间线 |
| `.refs` | 引用来源 chips |
| `.typing` | 打字指示器（三个跳动圆点） |
| `.quick-chip` | 快捷回复标签 |

---

## 10. 页面组装示例

> **规则**：先设计/复用组件，再拼成页面；JS 中禁止写内联 `style="…"`。

### 10.1 一个带加载、空状态、数据表格的页面

```js
// 初始化骨架
root.innerHTML = `
  <div class="page-head">
    <div class="page-title">文件管理</div>
    <div class="toolbar-spacer"></div>
    <button class="btn">刷新</button>
    <button class="btn btn-primary">导入</button>
  </div>
  <div class="progress hidden" id="pg"><i></i></div>
  <div class="page-panel glass panel">
    <div class="scroll-area" id="list"></div>
  </div>`;

// 加载中
list.innerHTML = `<div class="hint">${t("common.loading")}</div>`;

// 空状态
list.innerHTML = `
  <div class="empty">
    <div class="empty-icon">📁</div>
    <div class="empty-title">暂无文件</div>
  </div>`;

// 数据表格
list.innerHTML = `
  <table class="table">
    <thead><tr>
      <th>文件名</th>
      <th class="col-status">状态</th>
      <th class="col-num">页数</th>
      <th class="col-actions"></th>
    </tr></thead>
    <tbody>
      <tr>
        <td>report.pdf</td>
        <td><span class="badge badge-success">已完成</span></td>
        <td>12</td>
        <td class="text-right">
          <button class="btn btn-sm btn-danger">删除</button>
        </td>
      </tr>
    </tbody>
  </table>`;
```

### 10.2 设置页中的一个区块

```js
sec.innerHTML = `
  <div class="section-title">语言</div>
  <div class="section-hint">切换界面显示语言</div>
  <div class="form-row">
    <select class="input" id="lang-select">
      <option>中文</option>
      <option>English</option>
    </select>
  </div>`;
```

---

## 11. 效果分级系统

### 11.1 分级框架

全站效果分三级，由 `QualityManager`（`js/quality.js`）自动检测并设置 `data-quality` 属性到 `<html>` 元素。

| 档位 | data-quality | 能力 |
|---|---|---|
| Basic | `basic` | 纯 CSS 半透明 + 阴影，无背景动效，无 backdrop-filter |
| High（默认） | `high` | backdrop-filter 玻璃 + 低流动背景 + 基础动效 |
| Ultra | `ultra` | 增强 blur/saturate + 完整背景动效 + 弹性动效 |

**驱动方式**：CSS 变量覆盖 + `:root[data-quality]` 选择器。JS 只负责检测和设置属性，不写死样式。

**手动切换**：`localStorage.setItem('quality-preference', 'high')`，设为 `'auto'` 恢复自动检测。

### 11.2 弹性缓动曲线

| 变量 | 曲线 | 用途 |
|---|---|---|
| `--ease-elastic` | cubic-bezier(0.34, 1.56, 0.64, 1) | 回弹出现 |
| `--ease-soft` | cubic-bezier(0.22, 1, 0.36, 1) | 常规过渡 |
| `--ease-fluid` | cubic-bezier(0.4, 0, 0.2, 1) | 流体动画 |
| `--ease-spring` | cubic-bezier(0.68, -0.55, 0.265, 1.55) | 弹簧物理 |

### 11.3 动效工具类

| 类名 | 效果 |
|---|---|
| `.animate-elastic-in` | 弹性缩放出现 |
| `.animate-breathe` | 呼吸缩放（用于 AI 头像） |
| `.animate-glow-pulse` | 发光脉冲 |

### 11.4 发光输入容器 `.chat-input-wrap`

包裹 textarea 的玻璃发光容器，聚焦时泛起强调色光晕。

```html
<div class="chat-input-wrap">
  <textarea class="input chat-input" rows="1"></textarea>
</div>
```

聚焦效果由 `:focus-within` 伪类驱动，无需 JS。

### 11.5 AI 有机头像

AI 消息头像带呼吸光晕效果：

```html
<div class="msg-avatar ai animate-breathe">🐆</div>
```

`animate-breathe` 类驱动 `breathe` keyframes 动画，配合 `::before` 伪元素的径向渐变光晕。

### 11.6 消息弹性出现

消息行使用 `elasticIn` 动画替代旧的 `msgIn`：

```css
.msg-row { animation: elasticIn 0.5s var(--ease-soft) forwards; }
```

---

## 12. 知识库仪表盘组件

> 知识库页（`js/knowledge.js`）专用：分类圆环 + 下钻详情 + 随机知识卡片条带。`.kn-dash` 加 `.drilled` 类进入下钻态（圆环收缩到左侧，详情展开，过渡 0.4s `var(--ease-soft)`）。

### 12.1 仪表盘骨架

```html
<div class="kn-dash glass panel">          <!-- 仪表盘容器；.drilled = 下钻态 -->
  <div class="kn-main">
    <div class="kn-donut-wrap">…SVG…</div> <!-- 圆环区（下钻时收缩为 280px） -->
    <div class="kn-detail">…</div>         <!-- 分类详情（未下钻时收起） -->
  </div>
  <div class="kn-cards-title">…</div>      <!-- “随机知识”标题行 -->
  <div class="kn-cards">…</div>            <!-- 3 行卡片条带 -->
</div>
```

### 12.2 圆环图

| 类名 | 说明 |
|------|------|
| `.kn-donut` | SVG 圆环（弧段由 JS 用 stroke-dasharray 计算） |
| `.kn-track` | 底圈轨道 |
| `.kn-seg` | 分类弧段，颜色由 `.dc-*` 提供，选中加 `.sel` |
| `.dc-1` ~ `.dc-8` | 8 个弧段配色（基于现有强调色变量，循环取色） |
| `.kn-donut-center` / `.kn-total` / `.kn-total-label` | 中心总数与标签 |

```html
<svg class="kn-donut" viewBox="0 0 120 120">
  <circle class="kn-track" cx="60" cy="60" r="46"/>
  <circle class="kn-seg dc-1 sel" cx="60" cy="60" r="46"
          stroke-dasharray="120 169" stroke-dashoffset="0"/>
</svg>
```

### 12.3 下钻详情

| 类名 | 说明 |
|------|------|
| `.kn-breadcrumb` / `.kn-crumb` / `.kn-crumb-sep` | 面包屑（`.cur` 为当前级，可点击回跳） |
| `.kn-cat-name` / `.kn-cat-count` | 分类名 / 条目数 |
| `.kn-chips` / `.kn-chip` / `.kn-chip-count` | 子分类 chips |

```html
<div class="kn-breadcrumb">
  <span class="kn-crumb">全部</span><span class="kn-crumb-sep">/</span>
  <span class="kn-crumb cur">技术</span>
</div>
<div class="kn-chips">
  <button class="kn-chip">前端<span class="kn-chip-count">12</span></button>
</div>
```

### 12.4 随机知识卡片

| 类名 | 说明 |
|------|------|
| `.kn-cards-title` / `.kn-cards-label` | 标题行（含“换一批”按钮） |
| `.kn-card-row` | 单行横向可滚动条带 |
| `.kn-card` | 固定高圆角卡片（`.kn-card-text` 摘要 + `.kn-card-meta` 来源） |

```html
<div class="kn-card-row">
  <div class="kn-card">
    <div class="kn-card-text">知识内容摘要…</div>
    <div class="kn-card-meta">report.pdf · 第 3 页</div>
  </div>
</div>
```

### 12.5 Markdown 渲染类（renderMarkdown）

`app.js` 的 `renderMarkdown()` 输出以下语义化类，聊天气泡等场景通用：

| 类名 | 说明 |
|------|------|
| `.md-pre` | 代码块（深色半透明底 + 等宽字体，`data-lang` 角标显示语言） |
| `.md-code` | 行内代码 |
| `.md-h1` ~ `.md-h4` | 标题 `#` ~ `####` |
| `.md-ul` / `.md-ol` | 无序 / 有序列表 |
| `.md-quote` | 引用 `>` |
| `.md-link` | 链接（点击经 `api("open_external", url)` 打开） |
| `.md-table` | 表格（`|a|b|` 形式） |

```js
bubble.innerHTML = renderMarkdown(text);
```

---

## 附录：禁止清单

| ❌ 禁止做法 | ✅ 正确做法 |
|-----------|-----------|
| `el.style.display = 'none'` | `el.classList.add('hidden')` |
| `style="color:var(--text-muted)"` | `class="hint"` 或 `class="text-muted"` |
| `style="font-size:var(--fs-xs)"` | `class="hint-xs"` |
| `style="margin-top:6px"` | `class="mt-s"` |
| `style="width:120px"` | `class="col-status"` |
| `style="text-align:right"` | `class="text-right"` |
| `style="user-select:text"` | `class="selectable"` |
| 写死 `#22D3EE`、`rgba(…)` | 使用 `:root` 变量或语义化类 |

---

*文档版本：与 `app.css` 同步维护。新增组件时同步更新本文件。*
