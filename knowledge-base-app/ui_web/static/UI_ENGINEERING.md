# 知识学爆 · Web UI 工程实用文档（液态玻璃 × 有机美学）

> 状态：**规划阶段**（本阶段仅产出工程文档，不落地代码）
> 依据：《液态玻璃 × 有机美学 技术调研文档》(feishu.doubao.com/docx/EjjXd72nioAvJFxCWbMc54NlnZe)
> 目标页面：`ui_web/`（pywebview + 原生 HTML/CSS/JS）

---

## 0. 文档定位

本文档是 Web UI 大幅度优化的**唯一工程依据**，用于回答三个问题：

1. **做什么** —— 本次优化的技术路线与视觉风格（源自调研文档 §1 `技术选型与架构总览`）。
2. **怎么做** —— 组件优先的架构纪律，杜绝硬编码（项目规则）。
3. **落到哪** —— 组件如何组织、如何整合进四个页面、逐条写入 UI 组件文档。

> 组件**逐个的用法说明**沉淀在 [UI_COMPONENTS.md](./UI_COMPONENTS.md)（本文件只定架构与规则，UI_COMPONENTS.md 只写用法，二者单向引用、分工明确）。

---

## 1. 技术路线决策（源自调研文档 §1）

### 1.1 总体结论

采纳调研文档 §1.2 的**分层混合架构**，不采用"全 WebGL"激进方案。理由：

- pywebview 的 Chromium(EdgeChromium) 对 `backdrop-filter`、CSS 变量、Canvas 2D 支持完善，**CSS 基线即可覆盖绝大多数设备**；
- 不做"全 WebGL UI"（收益低、成本高、降级复杂）；但**玻璃材质本身**在 high/ultra 档用 WebGL 片元着色器渲染，basic 档回落到纯 CSS；
- 现有 Web UI 已具备 aurora 背景 + 玻璃面板，与推荐架构天然契合，改造是"规范化 + 增强"，而非推倒重来。

### 1.2 技术栈（锁定）

| 层 | 选型 | 说明 |
|---|---|---|
| 渲染 | 原生 HTML + CSS3 | 无框架，保持轻量，与 pywebview 静态资源加载方式一致 |
| 样式系统 | **CSS 变量（设计令牌）+ 语义化类** | 已存在于 `app.css :root`，作为全站唯一事实源 |
| 玻璃材质 | `backdrop-filter`（basic 回落）+ **WebGL 片元着色器（high/ultra）** | basic 纯 CSS；high/ultra 用 WebGL 渲染折射/高光 |
| 背景动效 | Canvas 2D 有机 blob 流动 | 承接现有 `.aurora`，规范化性能与降级 |
| 高级特效 | SVG `feDisplacementMap`（可选/降级增强） | 可作为 WebGL 不可用时的折射替代 |
| 动效 | CSS 动画 / 弹性缓动曲线 | 复杂时间线先不引入 GSAP，保持零依赖 |
| 性能 | requestAnimationFrame + FPS 计数 + 效果分级 | 仅背景动画需要，组件动画走 CSS |

### 1.3 与 pywebview 的集成约束（沿用既有约定）

- 无边框窗口 + 自绘标题栏 / 缩放热区，均走既有 `app.js` 自绘逻辑与 `bridge.py` 桥接，**本次不重做**。
- 全程启用 GPU 硬件加速：`backdrop-filter` 与 WebGL 依赖 GPU，需在 EdgeChromium 后端确认开启。
- 窗口拖拽/缩放期间，对 `backdrop-filter` 做**降级（关闭模糊）**以保流畅——对应调研 §3.1 的 `.resizing` 优化，作为组件级规则固化。

### 1.4 效果分级（三级体系，全站主线）

| 档位 | data-quality | 能力 | 目标 FPS |
|---|---|---|---|
| Ultra | `ultra` | WebGL 玻璃（色散 + 菲涅尔 + 高光）+ 动态 blob + 弹性动效 | ≥60 |
| High（默认） | `high` | WebGL 玻璃（基础折射 + 高光）+ 低流动 blob + 基础动效 | ≥45 |
| Basic | `basic` | 纯 CSS 半透明 + 阴影 + 无背景动效 | ≥60 |

**驱动方式（CSS 变量，非 JS 硬切）**：全站分级由 `:root[data-quality="…"]` 一段覆盖设计令牌实现；JS 只负责检测与设置 `data-quality`，不写死任何样式。分级来源：设备检测（WebGL 支持、CPU 核数、内存）→ 手动偏好（localStorage）。

---

## 2. 视觉风格规范

### 2.1 风格定调

**液态玻璃（Liquid Glass）× 有机美学（Organic Aesthetics）**，深空靛蓝基底：

- **基底**：暗色深邃渐变（青、紫、粉三团极光光斑缓慢流动），营造"环境光穿透玻璃"的悬浮感。
- **材质**：玻璃面板分三层——半透明基色 → 镜面高光 → 折射描边；叠加底部内阴影（厚度）与顶部亮边（透镜感）。
- **动效**：弹性缓动曲线（回弹、流体、呼吸），一切交互有反馈但不过度。
- **色彩**：青 `accent` 与紫 `accent-violet` 为主强调，粉 `blob-pink` 点缀；用户消息=青调，AI 消息=紫调。

### 2.2 设计令牌（Design Tokens）

全部集中定义于 `app.css :root`，**任何组件/页面禁止再写死色值、圆角、间距、字号、动效时长**。分类一览（已存在，沿用）：

| 类别 | 变量示例 | 用途 |
|---|---|---|
| 基底 | `--bg-top / --bg-mid / --bg-bottom` | 页面渐变底色 |
| 光斑 | `--blob-cyan / --blob-violet / --blob-pink` | aurora 流动环境光 |
| 文字 | `--text-primary / -secondary / -muted` | 三级文字 |
| 玻璃三层 | `--glass-fill-* / --glass-specular / --glass-border-* / --glass-inner-shadow` | `.glass` 材质 |
| 强调 | `--accent / --accent-violet / --danger / --success / --warning` (+`*-soft`) | 主/危/成/警 |
| 圆角 | `--r-s / -m / -l / -xl / -window` | 8/12/18/24/16px |
| 间距 | `--sp-xs ~ --sp-xxl` | 4/8/12/16/24/32px |
| 字号 | `--fs-xs ~ --fs-title` | 10/12/14/17/22/26px |
| 动效 | `--anim-fast / -med / -slow` | 120/220/420ms |

> 原则：**改主题只改 `:root`，全站自动跟随。**

### 2.3 玻璃材质分层（组件级固化）

每个玻璃组件遵循统一的分层语言（由 `.glass` 基类承载，组件按需叠加）：

1. 悬浮投影（3D 深度）
2. 折射描边（`--glass-border-*`）
3. 半透明基色（`--glass-fill-*`）
4. 底部内阴影（厚度感）
5. 顶部镜面高光（`--glass-specular`）
6. 顶部亮边（透镜边缘光）

小组件（按钮/徽标/列表项）可关闭投影与流光以控性能；大面板（面板/输入容器/气泡）保留完整分层。

### 2.4 动效曲线（全局统一）

| 用途 | 曲线语义 | 令牌 |
|---|---|---|
| 常规过渡 | 缓出（soft） | `--anim-med` |
| 出现/弹性 | 回弹（elastic） | 弹性缓动 |
| 持续背景 | 呼吸/浮动 | `breathe` / `float` |

所有动效时长取自令牌；**禁止**散落的 `transition: .3s` 等裸值。

---

## 3. 组件化架构（项目规则落地）

### 3.1 分层依赖（严格单向）

```
设计令牌(:root) → 基础原语(primitive) → 组件(component) → 页面(page) → 窗口骨架(Main)
页面/组件 ──调用──> bridge.js ──转发──> bridge.py ──> services / workers
```

- 下层绝不能反向依赖上层；组件不得直接读取页面状态。
- JS 只做**结构拼接 + 行为**，视觉全部由语义化 CSS 类承担（见 UI_COMPONENTS.md 附录"禁止清单"）。

### 3.2 杜绝硬编码（硬性规则）

1. 颜色 / 圆角 / 间距 / 字号 / 动效时长 → 一律取 `:root` 令牌或语义化类。
2. 文案 → 一律走 `data-i18n` 国际化，禁止硬编码中文字符串。
3. 显隐 → `classList` 切换 `.hidden`，禁止 `style.display`。
4. 对齐 / 截断 / 颜色 → 语义化工具类（`.text-right / .break-all / .hint / .text-danger` 等）。
5. 进度 / 状态 → 语义化类（`.col-status` 等），禁止内联宽度魔法数。

> 新增任何样式能力，先问"是否已有令牌/类可复用"，没有再新建并**同步登记到 UI_COMPONENTS.md**。

### 3.3 组件清单（Inventory）

按 DOM 结构维度组织，涵盖现有类并规划本次增强。**每个组件的详细属性 / 用法 / 变体写入 UI_COMPONENTS.md**，此处仅维护目录索引。

| 分组 | 组件 | 状态 | 说明（本次动作） |
|---|---|---|---|
| **原语** | `.glass` 玻璃面板 | 有 | 规范化分层语言 + 分级降级 |
| | `.btn` 系列 | 有 | 变体对齐（primary/ghost/danger） |
| | `.badge` / `.progress` / `.switch` / `.checkbox` | 有 | 沿用 |
| | `.input` / `.form-row` / `.pill-toggle` / `.table.col-*` | 有 | 沿用 |
| **布局** | `#titlebar` / `#navrail` / `#statusbar` | 有 | 沿用，纳入骨架组 |
| | `.page-head` / `.page-panel` / `.page-body` / `.scroll-area` | 有 | 沿用 |
| **反馈** | `#toast` / `#modal-root` / `.empty` | 有 | 沿用 |
| **对话** | `.chat-sidebar` / `.chat-main` | 有 | 沿用 |
| | `.msg-avatar` / `.bubble` | 有 | 升级为玻璃质感（AI 头像呼吸光晕） |
| | `.thinking-box` / `.steps` / `.refs` | 有 | 沿用 |
| | `.typing` / `.quick-chip` | 有 | 沿用 |
| **输入容器** | 底部发光输入容器（含工具栏 + 自动高度） | 规划 | 新增：完整"玻璃输入容器"组件 |
| **背景** | `.aurora` Canvas 动效 | 有 | 规范化分级 + FPS 降级 |

---

## 4. 组件 → 页面的整合映射

每个页面由"复用既有组件 + 少量专属组件"拼装，**禁止在页面里写内联样式**。

| 页面 | 主导组件 | 专属组件 | 落地要点 |
|---|---|---|---|
| 对话 Chat | chat-sidebar、msg-avatar、bubble、thinking-box、steps、refs、typing、quick-chip | 发光输入容器、AI 有机头像 | 流式消息、思考折叠、引用、快捷提问 |
| 文件 Files | table、badge、progress、btn | 空状态 | 状态徽标、页数、导入进度、删除确认 |
| 知识库 Knowledge | table、badge、btn | 分类列表 | 分类 + chunk 数、向量库重建（确认+进度+结果） |
| 设置 Settings | form-row、input、switch、checkbox、pill-toggle、btn | 依赖/日志面板 | 模型配置、凭据、语言、方案选择 |

---

## 5. 实施阶段规划（渐进式增强）

> 调研文档 §1.3 建议：**先 CSS 基线 → 再 SVG 增强 → 最后 WebGL 可选**，每步带完整降级。本工程照此执行。

| 阶段 | 内容 | 验收 |
|---|---|---|
| **P0 规范基线** | 固化令牌、`.glass` 分层、动效曲线；接入 `data-quality` 分级框架 | 全站无裸值；切换档位即生效 |
| **P1 组件标准化** | 补齐/标准化组件清单（含新增输入容器、AI 头像）；逐条写入 UI_COMPONENTS.md | 组件可独立复用，页面纯拼装 |
| **P2 动效增强** | 有机 blob 规范化分级、弹性动效、头像呼吸、消息流式出现 | 背景动画 FPS 达标，交互有反馈 |
| **P3 高级增强（可选）** | WebGL 玻璃片元着色器（high/ultra 档）；SVG 折射作为 WebGL 不可用时的降级 | 玻璃在 high/ultra 走 WebGL，basic 无感回落纯 CSS |

---

## 6. 验收与质量门禁

1. **无硬编码审计**：全站 `grep` 不出现裸色值 / 裸时长 / `style="…"`（设置动态宽度的进度条除外，走语义类）。
2. **组件可复用**：同一组件多页复用，未出现复制粘贴式页面样式。
3. **分级正确**：basic / high / ultra 三档下玻璃与动效均正常，basic 无背景动画。
4. **文档同步**：新增/改动组件后，UI_COMPONENTS.md 同步更新；本文件为架构唯一来源。
5. **冒烟回归**：`tests/test_ui_smoke.py` 通过，四个页面可正常加载与交互。

---

*版本：v0.1（规划）。与 `app.css` / `UI_COMPONENTS.md` 同步维护。*