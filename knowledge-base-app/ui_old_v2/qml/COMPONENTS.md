# 知识学爆 · Cheese Snow Leopard — 液态玻璃 UI 组件使用说明

本文档覆盖新 UI（`ui/` 目录）的全部 QML 组件、设计令牌、页面与桥接层的使用方式。
旧 UI 已归档至 `ui_old/`，不再更新，也不由启动脚本拉起。

## 1. 架构总览

```
ui/
├── app.py                  # 装配入口 run_ui()：创建 QApplication、桥接层、QML 引擎
├── i18n.py                 # 多语言服务（context property: i18n）
├── window_effects.py       # Windows DWM 亚克力/圆角（其他平台静默回退）
├── bridges/                # Python ↔ QML 桥接层（只转发，不含业务逻辑）
│   ├── chat_bridge.py      #   context property: chatBridge
│   ├── files_bridge.py     #   context property: filesBridge
│   ├── knowledge_bridge.py #   context property: knowledgeBridge
│   └── settings_bridge.py  #   context property: settingsBridge
├── i18n/                   # 词典：zh_CN.json / en_US.json
└── qml/
    ├── Main.qml            # 主窗口（无边框 + 导航 + 页面栈 + 状态栏 + Toast + 边缘缩放）
    ├── theme/Theme.qml     # 设计令牌单例（pragma Singleton）
    ├── components/         # 17 个可复用玻璃组件
    └── pages/              # 4 个页面（ChatPage / FilesPage / KnowledgePage / SettingsPage）
```

分层规则（严格单向依赖）：

```
Theme（设计令牌） → components（组件） → pages（页面） → Main.qml（窗口）
pages/components ──调用──> Bridge（context property） ──转发──> services / workers
```

## 2. 硬性约定

1. **禁止硬编码**：颜色、圆角、间距、字号、动效时长一律引用 `Theme.*`；文案一律走 `i18n.tr()`。
2. **文案绑定写法**（保证语言切换即时刷新）：

   ```qml
   Text { text: (i18n.language, i18n.tr("nav.chat")) }
   // 带占位符：
   Text { text: (i18n.language, i18n.trf("files.imported", { "count": 3 })) }
   ```

   逗号表达式让绑定注册对 `i18n.language` 的依赖；`languageChanged` 触发时全部文本自动重求值。
3. **确认框/提示**：业务确认一律用 `GlassDialog.openConfirm(...)`，轻提示由 Bridge 发 `infoMessage`/`errorMessage` 信号，Main.qml 统一弹 `GlassToast`。
4. **耗时操作**：只允许放在 Python Worker/QThread，QML 通过 Bridge 信号接收进度，UI 线程永不阻塞。

## 3. Theme 设计令牌（theme/Theme.qml）

单例，`import "../theme"` 后直接使用（components 内）或 `import "theme"`（qml 根目录）。

| 分组 | 令牌 | 说明 |
|---|---|---|
| 基底 | `bgTop / bgMid / bgBottom` | 深空靛蓝渐变（带 alpha，透出 DWM 亚克力） |
| 光斑 | `blobCyan / blobViolet / blobPink` | AuroraBackground 流动环境光 |
| 文字 | `textPrimary / textSecondary / textMuted` | 三级文字色 |
| 玻璃三层 | `glassFillTop / glassFillBottom`（层1 基色）、`glassSpecular`（层2 高光）、`glassBorderTop / glassBorderBottom`（层3 折射描边） | 所有玻璃材质的标准配色 |
| 强调色 | `accent`（青）`accentViolet`（紫）`danger / success / warning` 及各自 `*Soft` 弱填充 | |
| 气泡 | `bubbleUserTop/Bottom/Border`、`bubbleAiTop/Bottom/Border` | 用户=青调，AI=紫调 |
| 圆角 | `radiusS 8 / radiusM 12 / radiusL 18 / radiusXL 24 / radiusWindow 16` | |
| 间距 | `spaceXS 4 / spaceS 8 / spaceM 12 / spaceL 16 / spaceXL 24 / spaceXXL 32` | |
| 字号 | `fontXS 10 / fontS 12 / fontM 14 / fontL 17 / fontXL 22 / fontTitle 26` | |
| 动效 | `animFast 120 / animMed 220 / animSlow 420`（ms） | |
| 结构 | `navWidth / titleBarHeight / statusBarHeight / buttonHeight / inputHeight / avatarSize / windowMargin` | |

## 4. 基础组件（components/）

### GlassPanel — 玻璃面板（万物之基）

真 3D 液态玻璃材质系统（参考 Apple Liquid Glass），材质分层（底→顶）：
悬浮投影 → 折射描边 → 半透明基色 → 底部内阴影（厚度感）→ 底部焦散（环境色折射亮线）
→ 对角流光（内部发光）→ 顶部镜面高光 → 顶部亮边。

```qml
GlassPanel {
    Layout.fillWidth: true
    radius: Theme.radiusXL          // 默认 Theme.radiusL
    specularOpacity: 0.45           // 高光强度，0 = 关闭
    shadow: true                    // 悬浮投影（3D 深度）；按钮/徽标/列表项等小组件建议 false
    sheen: true                     // 对角流光；小组件建议 false
    edgeLight: true                 // 边缘透镜光（顶部亮边 + 底部焦散 + 内阴影）
    causticColor: Theme.accent      // 焦散色调（默认主强调色，气泡按 tone 覆写）
    glow: field.activeFocus         // 外部辉光（聚焦/激活）
    glowColor: Theme.accent
    fillTop: ... / fillBottom: ... / borderTop: ... / borderBottom: ...  // 可覆写
    // 子元素默认放入内容区（自动内缩 1px 避开描边）
}
```

### GlassButton — 玻璃按钮

```qml
GlassButton {
    text: (i18n.language, i18n.tr("common.save"))
    variant: "primary"              // primary(青,悬停辉光) | ghost(中性) | danger(红)
    enabled: !bridge.running
    onClicked: bridge.save()
}
```

信号：`clicked()`。自带按下微缩回弹、悬停加亮。

### GlassIconButton — 紧凑图标按钮

```qml
GlassIconButton {
    glyph: "🗑"                     // 文字符号作图标
    tip: (i18n.language, i18n.tr("files.delete"))   // 悬停提示（自绘玻璃 tooltip）
    danger: true                    // 悬停变红
    size: 30
    onClicked: ...
}
```

### GlassInput — 单行输入框

```qml
GlassInput {
    Layout.fillWidth: true
    placeholder: (i18n.language, i18n.tr("settings.apiKeyPlaceholder"))
    echoMode: TextInput.Password    // 通过 alias 直设
    text: ""                        // property alias，双向绑定
    onAccepted: ...                 // 回车
    onTextEdited: ...               // 用户编辑（程序化 setText 不触发）
}
```

聚焦时自动泛起 `Theme.accent` 辉光。

### GlassComboBox — 下拉选择

```qml
GlassComboBox {
    model: i18n.availableLanguages  // [{code, name}] 或字符串数组
    displayRole: "name"             // 对象数组时取该字段显示（默认 "label"）
    currentIndex: 0
    placeholder: (i18n.language, i18n.tr("chat.model"))
    onActivated: function(index, item) { i18n.language = item.code }
}
```

只读 `currentText` 可用于外部展示。弹出层为模态玻璃列表，Esc/点击外部关闭。

### GlassCheckBox / GlassSwitch — 选择控件

```qml
GlassCheckBox {
    text: modelData.displayName     // 可为空（纯方框）
    checked: modelData.enabled
    onToggled: function(c) { checked = c; /* 自行持久化 */ }
}
GlassSwitch {
    checked: chatBridge.thinking
    onToggled: function(c) { chatBridge.thinking = c }
}
```

注意：`toggled(bool)` 只发信号，**不会自动改 `checked`**，需在处理函数里显式赋值（避免绑定环）。

### GlassBadge — 状态徽标胶囊

```qml
GlassBadge { text: i18n.tr(modelData.statusKey); tone: "success" }
// tone: info(青) | success(绿) | warning(黄) | danger(红) | muted(灰)
```

### GlassAvatar — 悬浮玻璃头像

```qml
GlassAvatar { role: "assistant"; text: "AI"; size: Theme.avatarSize }
// role: user(青调) | assistant(紫调)，外圈带色调辉光环
```

### GlassProgressBar — 进度条

```qml
GlassProgressBar {
    value: 0.42                     // 0..1 确定进度（青→紫渐变填充）
    indeterminate: false            // true 时流光往返（未知进度）
    text: "正在解析…"               // 可选附加说明
}
```

### GlassDialog — 模态对话框

```qml
GlassDialog { id: delDlg }

// 确认框：
delDlg.openConfirm("删除文件", "删除后不可恢复，确定？", function() {
    filesBridge.deleteDocument(docId)
}, true)                            // 第 4 参 danger=true → 确认键变红

// 仅提示（单按钮）：
dlg.singleButton = true
dlg.openCustom("警告")
dlg.message = "部分功能不可用"

// 自定义内容（塞进默认属性）+ 隐藏按钮区：
// dlg.dialogWidth = 560; dlg.hideButtons = true; dlg.openCustom("标题")
```

属性：`title / message / confirmText / cancelText / dangerConfirm / hideButtons / singleButton / dialogWidth / dialogHeight(-1 自适应)`。

### GlassToast — 轻提示（宿主放置，全局复用）

```qml
GlassToast { id: toast; anchors.horizontalCenter: parent.horizontalCenter; z: 1000 }
toast.show("保存成功")              // 信息样式
toast.show("删除失败", true)        // 错误样式（红调）
```

`duration` 默认 2800ms，自动消隐。Main.qml 已全局接入各 Bridge 的 `infoMessage/errorMessage`。

### MessageBubble — 聊天消息气泡

```qml
MessageBubble {
    role: "assistant"               // user(青,靠右) | assistant(紫,靠左)
    text: mdContent                 // assistant 自动按 Markdown 渲染
    reasoning: thinkingText         // 思考过程（可折叠面板，空串则不显示）
    steps: [{kind, status, detail}] // 多步时间线：思考/检索/回答（进行中呼吸点，完成✓；
                                    //   检索步骤显示查询词与命中数，空数组则不显示）
    refs: [{chunk_id, source_file, page, type, excerpt}]   // 引用来源（点击展开摘录）
    streaming: true                 // 流式中：辉光 + 光标 ▍；text 为空时显示 TypingIndicator
    isError: false                  // 错误消息（红字）
    maxBubbleWidth: 620
}
```

头像自动悬浮在气泡上缘外侧。

### TypingIndicator — 流动打字指示器

```qml
TypingIndicator { color: Theme.accentViolet; dotSize: 8 }
```

三颗玻璃珠依次起伏，`visible` 为 false 时动画自动停止。

### NavRailButton — 侧边导航按钮

```qml
NavRailButton {
    icon: "💬"; text: (i18n.language, i18n.tr("nav.chat"))
    active: win.page === 0
    onClicked: win.page = 0
}
```

激活态：青色玻璃 + 左侧光条动画。

### TitleBar — 自定义标题栏

```qml
TitleBar {
    targetWindow: win               // ApplicationWindow 引用（拖动/最小化/最大化/关闭）
    title: (i18n.language, i18n.tr("app.title"))
}
```

拖动走 `startSystemMove()`（Windows Snap 兼容），双击切换最大化。

### AuroraBackground — 极光渐变背景（窗口最底层）

```qml
AuroraBackground { anchors.fill: parent; rounded: !win.maximized }
```

深空渐变 + 三团缓慢流动的环境光斑（青/紫/粉）+ 顶部微高光。仅在窗口可见时运行动画。

## 5. 页面（pages/）

| 页面 | 桥接 | 对外接口 | 功能 |
|---|---|---|---|
| ChatPage | chatBridge | `signal requestNavigate(int page)` | 会话列表（新建/选择/⋯对话设置）、消息流（流式/思考折叠/引用）、模型选择、思考模式开关、发光输入栏、快捷提问、空状态引导 |
| FilesPage | filesBridge | — | 文档列表（状态徽标/页数/删除）、导入进度条、删除确认 |
| KnowledgePage | knowledgeBridge | — | 分类列表（名称/chunk 数）、向量库重建（确认 + 进度 + 结果） |
| SettingsPage | settingsBridge | `signal modelsSaved()`（Main.qml 接到后调用 `chatBridge.reloadModels()`） | 语言切换、模型配置（厂商/API Key/启用）、默认模型、数据位置迁移、凭据管理、一键部署（实时日志）、依赖安装/卸载、方案选择 |

页面跳转示例（ChatPage 空状态"去设置"按钮）：

```qml
onRequestNavigate: function(page) { win.page = page }   // Main.qml 中接线
// ChatPage 内部：root.requestNavigate(3)
```

## 6. 桥接层速查

QML 中直接以 context property 名访问。所有耗时操作异步执行，结果经信号返回。

### chatBridge（对话）

- 属性：`conversations`、`currentConvId`、`generating`、`thinking`（可写）、`models`、`currentModelName`、`hasConfiguredModel`
- 方法：`newConversation()`、`selectConversation(id)`、`deleteConversation(id)`、`renameConversation(id, title)`、`setAutoName(id, enabled)`、`getConversationInfo(id)`、`send(text)`、`stop()`、`selectModel(pk, model, display)`、`reloadModels()`、`reAutoName(id)`
- 流式信号（ChatPage 已接）：`userMessageAppended / assistantMessageStarted / reasoningChunk / answerChunk / stepsUpdated / referencesAppended / streamFinished / assistantError`
  - `stepsUpdated(list)`：多步时间线 `[{kind: thinking|search|answer, status: running|done, detail}]`。思考/回答步骤由桥接层从 token 流派生；检索步骤由 RAG 工具调用发出（detail = 查询词 → 命中数）。
- 其他信号：`conversationsChanged / generatingChanged / thinkingChanged / modelsChanged / currentModelChanged / titleUpdated / infoMessage / statusMessage`

### filesBridge（文件）

- 属性：`documents`（[{docId, fileName, status, statusKey, pageCount}]）、`importRunning`
- 方法：`refresh()`、`importFiles()`（自带文件选择框）、`deleteDocument(docId)`
- 信号：`documentsChanged / importProgress(percent, msg) / importRunningChanged / infoMessage / errorMessage / statusMessage`

### knowledgeBridge（知识库）

- 属性：`categories`（[{name, chunkCount}]）、`rebuilding`
- 方法：`refresh()`、`rebuild()`
- 信号：`categoriesChanged / rebuildingChanged / rebuildProgress / rebuildFinishedOk / infoMessage / errorMessage / statusMessage`

### settingsBridge（设置）

- 属性：`providers`、`enabledModels`、`defaultRoles`、`credentials`、`coreDependencies`、`optionalComponents`、`depRunning`、`bootstrapRunning`、`migrateRunning`、`dataRoot`、`vlmScheme`、`embedScheme`
- 方法：`saveApiKey / clearApiKey / saveModelStates / testConnection / openKeyApplyUrl / setDefaultModel / notifyDefaultsSaved / pickDataDirectory / migrateData / saveCredentials / clearAllCredentials / runBootstrap / refreshDependencies / runDependencyTask(keys, install) / saveScheme(vlm, emb)`
- 信号：`testConnectionResult / depLogAppended / depFinished / bootstrapLogAppended / bootstrapFinished / migrateFinished` + 各 `*Changed` + `infoMessage / errorMessage / statusMessage`

## 7. 多语言（i18n）

- 词典：`ui/i18n/zh_CN.json`、`ui/i18n/en_US.json`，key 为点分层级（如 `settings.apiKeySaved`）。
- 当前语言持久化在 `config.yaml` 的 `ui.language`，启动时自动恢复。
- QML 绑定刷新写法见 §2；Python 侧用 `bridge._tr("key", **params)`。
- 新增语言：在 `i18n.py` 的 `LANGUAGES` 加条目 + 新增 `ui/i18n/<code>.json`（保持 key 全集一致）。
- 新增文案：两个词典**同时**补 key；`tr()` 缺失时回退默认语言再回退 key 本身。

## 8. 新增组件/页面清单

新增组件时：

1. 放 `ui/qml/components/`，文件名大驼峰，首行注释写明用途与用法；
2. 全部数值取 `Theme.*`，全部文案走 `i18n.tr()`；
3. 交互反馈遵守既有模式（悬停加亮 `animFast`、按下回弹、聚焦 `glow`）；
4. 耗时操作不得进 QML，扩展对应 Bridge 的 Slot + 信号；
5. 在 `tests/test_ui_smoke.py` 跑一遍确认无 QML 引用错误：

```powershell
.venv\Scripts\python.exe tests\test_ui_smoke.py
```
