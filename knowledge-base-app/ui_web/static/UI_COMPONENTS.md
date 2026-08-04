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
