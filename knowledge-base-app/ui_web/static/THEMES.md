# 主题创建指南

本指南说明 Cheese Snow Leopard Web UI 的主题系统接口，供快速创建自定义主题。

## 1. 主题系统原理

- 全部视觉表现由 **设计令牌（CSS 自定义属性）** 驱动，组件不硬编码颜色。
- 内置主题通过 `:root[data-theme="..."]` 选择器整体覆盖配色令牌：
  - `dark` — 默认暗夜主题（`:root` 无属性时的基础值）
  - `light` — 米白清新主题
- 自定义主题 = **基调（dark/light）** + **令牌覆盖表**。应用时先切到基调，
  再由 `ThemeManager` 将覆盖表内联写入 `<html>` 元素的 `style`。
- 结构类令牌（圆角、间距、字号、动效曲线）两个主题保持一致 —— 自定义主题
  只应覆盖 **配色类** 令牌，以保证风格统一。

## 2. 快速创建（推荐）

设置 → 外观 → 主题 → **新建主题**：

1. 填写主题名称
2. 选择基调（新建亮色主题选「米白清新」，暗色选「暗夜」）
3. 用色板调整 9 个核心颜色（见下表）
4. 需要更精细控制时，在「高级 JSON 令牌覆盖」中写入任意令牌
5. 保存后立即应用并自动持久化（localStorage，仅本机）

## 3. 核心色板字段（编辑器色板 ↔ 令牌）

| 编辑器字段 | 令牌 | 说明 |
|---|---|---|
| 背景·顶部 | `--bg-top` | 页面渐变背景顶部 |
| 背景·中部 | `--bg-mid` | 页面渐变背景中部 |
| 背景·底部 | `--bg-bottom` | 页面渐变背景底部 |
| 光斑·青 | `--blob-cyan` | Aurora 光斑 1 |
| 光斑·紫 | `--blob-violet` | Aurora 光斑 2 |
| 光斑·粉 | `--blob-pink` | Aurora 光斑 3 |
| 强调色 | `--accent` | 主强调（按钮渐变、选中态、链接） |
| 辅助强调 | `--accent-violet` | 渐变终点、次级强调 |
| 主文字 | `--text-primary` | 一级文字色 |

> 注意：修改 `--accent` 不会自动联动 `--accent-a08…a60` 等 rgba 透明度变体
> 与 `--grad-from-85/--grad-to-85`。需要联动时请用高级 JSON 一并覆盖。

## 4. 完整令牌参考

### 4.1 配色令牌（主题可覆盖）

| 分组 | 令牌 |
|---|---|
| 基底 | `--bg-top` `--bg-mid` `--bg-bottom` `--blob-cyan` `--blob-violet` `--blob-pink` |
| 文字 | `--text-primary` `--text-secondary` `--text-muted` |
| 玻璃 | `--glass-fill-top` `--glass-fill-bottom` `--glass-border-top` `--glass-border-bottom` `--glass-specular` `--glass-inner-shadow` |
| 强调 | `--accent` `--accent-violet` `--accent-soft` `--accent-violet-soft` `--danger` `--danger-soft` `--success` `--success-soft` `--warning` `--warning-soft` |
| 渐变 | `--grad-from` `--grad-to` `--grad-from-85` `--grad-to-85` `--on-accent` |
| 透明度变体 | `--accent-a08/a18/a35/a40/a45/a50/a55/a60` `--violet-a50` `--success-a40/a60` `--danger-a35/a40/a45` `--warning-a40` `--muted-a12/a35` |
| 中性覆盖层 | `--ov-04` 至 `--ov-30`（共 14 级，边框/分隔/悬停层次） |
| 阴影/深底 | `--shadow-35` `--shadow-45` `--deep-55` `--deep-60` `--deep-65` `--field-bg` |
| 聊天气泡 | `--bubble-user-top/bottom/border` `--bubble-ai-top/bottom/border` |

### 4.2 结构令牌（不建议主题覆盖）

`--r-s/m/l/xl/window`（圆角）、`--sp-xs…xxl`（间距）、`--fs-xs…title`（字号）、
`--anim-fast/med/slow`、`--ease-elastic/soft/fluid/spring`、
`--nav-w` `--tb-h` `--sb-h` `--btn-h` `--input-h`、`--font-ui` `--font-mono`。

### 4.3 亮色主题的关键经验

- `--ov-*` 是"覆盖层"色阶：暗色主题为白色系 rgba，亮色主题必须翻转为深色系 rgba
  （参考 `app.css` 中 `[data-theme="light"]` 的实现）。
- `--deep-*` 用于日志框、代码块等"凹陷"底色：亮色主题用半透明白/米色。
- 强调色在亮底上需加深（如青 `#22D3EE` → `#0CA5C0`）以保证对比度。

## 5. JSON 覆盖格式

键为令牌名（`--` 前缀可省略），值为合法 CSS 颜色/尺寸字符串：

```json
{
  "--bg-top": "#F3FAF4",
  "--bg-mid": "#EAF6EE",
  "--bg-bottom": "#E2F0E8",
  "--blob-cyan": "#6EE7B7",
  "--blob-violet": "#A5B4FC",
  "--blob-pink": "#FBCFE8",
  "--accent": "#10B981",
  "--accent-violet": "#818CF8",
  "--text-primary": "#24312B",
  "--accent-a08": "rgba(16,185,129,.08)",
  "--accent-a45": "rgba(16,185,129,.45)",
  "--grad-from-85": "rgba(16,185,129,.85)",
  "--grad-to-85": "rgba(129,140,248,.85)"
}
```

## 6. ThemeManager API

全局单例：`window.themeManager`（`js/theme.js`，页面加载时即初始化并应用上次主题）。

| 方法 | 签名 | 说明 |
|---|---|---|
| 列表 | `list() → [{id, name, builtin, base?}]` | 内置 + 自定义主题 |
| 应用 | `apply(id) → bool` | 切换主题并持久化；失败返回 false |
| 注册 | `register({name, base, tokens}) → id` | 新建自定义主题（base: `"dark"`/`"light"`） |
| 更新 | `update(id, {name?, base?, tokens?}) → bool` | 修改自定义主题；若为当前主题则立即重应用 |
| 删除 | `remove(id)` | 删除自定义主题；若删除当前主题自动回退 dark |
| 读取 | `get(id) → {id, name, base, tokens} \| null` | 完整定义（编辑器回填用） |
| 当前 | `themeManager.active` | 当前主题 id |

事件：主题切换后派发 `window` 事件 `themechange`，`detail.id` 为新主题 id。

## 7. 与画质分级的关系

画质（`:root[data-quality]`）与主题（`:root[data-theme]`）正交：
- `basic` 档会关闭模糊与光斑（`--blob-*` 置透明、玻璃改不透明），
  对两个内置主题分别适配（`[data-theme="light"][data-quality="basic"]`）。
- 自定义主题基于某个基调继承这些规则，无需额外处理。

## 8. 持久化位置

- 当前主题 id：`localStorage["theme-preference"]`
- 自定义主题列表：`localStorage["custom-themes"]`（JSON 数组）
- 仅保存在本机浏览器（pywebview WebView）存储中，不写入 config.yaml。
