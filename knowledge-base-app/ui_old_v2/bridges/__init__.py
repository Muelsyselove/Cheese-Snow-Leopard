"""Python ↔ QML 桥接层

每个 Bridge 是一个 QObject，通过 context property 暴露给 QML：
- chatBridge      ChatBridge      对话页（会话/消息/流式/模型/自动命名）
- filesBridge     FilesBridge     文件页（文档列表/导入/删除）
- knowledgeBridge KnowledgeBridge 知识库页（分类/重建向量库）
- settingsBridge  SettingsBridge  设置页（模型/默认模型/凭据/依赖/方案/部署/数据位置）

Bridge 不实现业务逻辑，全部转发到 services / workers，只承担：
线程信号转发、QML 友好的数据结构转换、状态属性暴露。
"""
from ui_old_v2.bridges.chat_bridge import ChatBridge
from ui_old_v2.bridges.files_bridge import FilesBridge
from ui_old_v2.bridges.knowledge_bridge import KnowledgeBridge
from ui_old_v2.bridges.settings_bridge import SettingsBridge

__all__ = ["ChatBridge", "FilesBridge", "KnowledgeBridge", "SettingsBridge"]
