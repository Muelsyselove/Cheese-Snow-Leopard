"""[DEPRECATED old_v2] 知识学爆 Cheese Snow Leopard — QML 液态玻璃 UI（PySide6 QtQuick/QML）

⚠️ 本 UI 系统已标记为 old_v2（2026-08-04 起），不再受系统支持和更新。
   默认 UI 为 Web 路线（ui_web/ + pywebview WebView2 内核）。
   仅通过 `python main.py --ui=qml` 回退启动本系统。

包结构：
- app.py            应用装配入口（创建桥接层 + QML 引擎）
- i18n.py           多语言服务（简体中文 / English，JSON 词典驱动）
- window_effects.py 原生窗口特效（Windows DWM 亚克力/圆角，其他平台自动回退）
- bridges/          Python ↔ QML 桥接层（复用 services / workers）
- qml/              QML 界面（theme 设计令牌 + components 组件 + pages 页面）
- COMPONENTS.md     全部 UI 组件使用说明
"""
