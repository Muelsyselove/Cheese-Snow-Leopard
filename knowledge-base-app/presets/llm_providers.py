"""国内常用大模型 API 预置配置

厂商 → 模型多级选择，用户只需填 API Key。
所有预置厂商都兼容 OpenAI 协议（/v1/chat/completions）。

模型名与 API base 均来自各厂商官方文档：
- DeepSeek: https://api-docs.deepseek.com/quick_start/pricing
- 通义千问: https://help.aliyun.com/zh/dashscope/developer-reference/compatibility-of-openai-with-dashscope
- Moonshot: https://platform.moonshot.cn/docs/introduction
- 智谱: https://open.bigmodel.cn/dev/api
- 百川: https://platform.baichuan-ai.com/docs/api
- MiniMax: https://platform.minimaxi.com/document/Models
- 零一万物: https://platform.lingyiwanwu.com/docs
- 讯飞星火: https://www.xfyun.cn/doc/spark/HTTP%E8%B0%83%E7%94%A8%E6%96%87%E6%A1%A3.html
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ModelPreset:
    """单个模型预置"""
    model_name: str           # 调用 API 时使用的 model 字段
    display_name: str         # 下拉框显示名
    max_tokens: int = 8192    # 默认最大输出 token
    context_window: int = 65536  # 上下文窗口大小（仅展示用）


@dataclass
class ProviderPreset:
    """单个厂商预置"""
    key: str                  # 厂商唯一标识
    display_name: str         # 厂商显示名
    api_base: str             # OpenAI 兼容 API base URL
    keyring_key: str          # keyring 中的凭据 key
    key_apply_url: str        # API Key 申请链接
    models: list[ModelPreset] = field(default_factory=list)
    doc_url: str = ""         # 文档链接


# 国内常用大模型厂商预置（均提供 OpenAI 兼容接口）
PROVIDERS: list[ProviderPreset] = [
    # ============================================================
    # DeepSeek 深度求索
    # 文档: https://api-docs.deepseek.com/quick_start/pricing
    # Base URL: https://api.deepseek.com （OpenAI 兼容用 /v1）
    # 上下文 1M，最大输出 384K
    # 注: deepseek-chat / deepseek-reasoner 2026-07-24 后对应 v4-flash 的非思考/思考模式
    # ============================================================
    ProviderPreset(
        key="deepseek",
        display_name="DeepSeek 深度求索",
        api_base="https://api.deepseek.com/v1",
        keyring_key="llm_api_key",
        key_apply_url="https://platform.deepseek.com/api_keys",
        doc_url="https://api-docs.deepseek.com/",
        models=[
            ModelPreset("deepseek-v4-flash", "DeepSeek-V4-Flash（通用旗舰，支持思考模式）",
                        max_tokens=8192, context_window=1048576),
            ModelPreset("deepseek-v4-pro", "DeepSeek-V4-Pro（推理增强）",
                        max_tokens=8192, context_window=1048576),
            ModelPreset("deepseek-chat", "deepseek-chat（兼容旧名，等同 V4-Flash 非思考）",
                        max_tokens=8192, context_window=1048576),
            ModelPreset("deepseek-reasoner", "deepseek-reasoner（兼容旧名，等同 V4-Flash 思考）",
                        max_tokens=8192, context_window=1048576),
        ],
    ),
    # ============================================================
    # 阿里云通义千问（百炼）
    # 文档: https://help.aliyun.com/zh/dashscope/developer-reference/compatibility-of-openai-with-dashscope
    # Base URL: https://dashscope.aliyuncs.com/compatible-mode/v1
    # ============================================================
    ProviderPreset(
        key="qwen",
        display_name="阿里云通义千问（百炼）",
        api_base="https://dashscope.aliyuncs.com/compatible-mode/v1",
        keyring_key="llm_api_key",
        key_apply_url="https://bailian.console.aliyun.com/?apiKey=1",
        doc_url="https://help.aliyun.com/zh/dashscope/developer-reference/compatibility-of-openai-with-dashscope",
        models=[
            # 千问 Max 系列（能力最强）
            ModelPreset("qwen3.6-max-preview", "Qwen3.6-Max-Preview（旗舰）",
                        max_tokens=8192, context_window=262144),
            ModelPreset("qwen3-max", "Qwen3-Max",
                        max_tokens=8192, context_window=32768),
            ModelPreset("qwen-max", "Qwen-Max（经典旗舰）",
                        max_tokens=8192, context_window=32768),
            # 千问 Plus 系列（性价比）
            ModelPreset("qwen3.6-plus", "Qwen3.6-Plus（多模态）",
                        max_tokens=8192, context_window=262144),
            ModelPreset("qwen3.5-plus", "Qwen3.5-Plus",
                        max_tokens=8192, context_window=131072),
            ModelPreset("qwen-plus", "Qwen-Plus（通用）",
                        max_tokens=8192, context_window=131072),
            # Flash 系列（快速）
            ModelPreset("qwen3.6-flash", "Qwen3.6-Flash（快速响应）",
                        max_tokens=8192, context_window=262144),
            ModelPreset("qwen-turbo", "Qwen-Turbo（轻量快速）",
                        max_tokens=8192, context_window=1000000),
            # 长文本
            ModelPreset("qwen-long", "Qwen-Long（长文本，千万字）",
                        max_tokens=8192, context_window=10000000),
        ],
    ),
    # ============================================================
    # Moonshot 月之暗面（Kimi）
    # 文档: https://platform.moonshot.cn/docs/introduction
    # Base URL: https://api.moonshot.cn/v1
    # 注: kimi-latest 已于 2026-01-28 停止新用户使用
    # ============================================================
    ProviderPreset(
        key="moonshot",
        display_name="Moonshot 月之暗面（Kimi）",
        api_base="https://api.moonshot.cn/v1",
        keyring_key="llm_api_key",
        key_apply_url="https://platform.moonshot.cn/console/api-keys",
        doc_url="https://platform.moonshot.cn/docs/introduction",
        models=[
            # Kimi K2.6（默认推荐，多模态）
            ModelPreset("kimi-k2.6", "Kimi K2.6（多模态旗舰，256K 上下文）",
                        max_tokens=8192, context_window=262144),
            # Kimi K2.5（多模态）
            ModelPreset("kimi-k2.5", "Kimi K2.5（多模态，视觉+文本）",
                        max_tokens=8192, context_window=262144),
            # K2 系列
            ModelPreset("kimi-k2-0905-preview", "Kimi K2-0905（Agentic Coding 增强）",
                        max_tokens=8192, context_window=262144),
            ModelPreset("kimi-k2-0711-preview", "Kimi K2-0711（1T MoE 基座）",
                        max_tokens=8192, context_window=131072),
            ModelPreset("kimi-k2-turbo-preview", "Kimi K2-Turbo（高速版，60-100 t/s）",
                        max_tokens=8192, context_window=262144),
            ModelPreset("kimi-k2-thinking", "Kimi K2-Thinking（长思考）",
                        max_tokens=8192, context_window=262144),
            ModelPreset("kimi-k2-thinking-turbo", "Kimi K2-Thinking-Turbo（长思考高速版）",
                        max_tokens=8192, context_window=262144),
            # moonshot-v1 经典系列
            ModelPreset("moonshot-v1-128k", "Moonshot v1（128K 上下文）",
                        max_tokens=8192, context_window=131072),
            ModelPreset("moonshot-v1-32k", "Moonshot v1（32K 上下文）",
                        max_tokens=8192, context_window=32768),
            ModelPreset("moonshot-v1-8k", "Moonshot v1（8K 上下文）",
                        max_tokens=8192, context_window=8192),
        ],
    ),
    # ============================================================
    # 智谱 AI（GLM）
    # 文档: https://open.bigmodel.cn/dev/api
    # Base URL: https://open.bigmodel.cn/api/paas/v4
    # GLM-5.2: 2026.6 全量开放，745B MoE 旗舰
    # GLM-4.6: Agentic Coding 增强
    # ============================================================
    ProviderPreset(
        key="zhipu",
        display_name="智谱 AI（GLM）",
        api_base="https://open.bigmodel.cn/api/paas/v4",
        keyring_key="llm_api_key",
        key_apply_url="https://open.bigmodel.cn/usercenter/apikeys",
        doc_url="https://open.bigmodel.cn/dev/api",
        models=[
            # GLM-5 系列
            ModelPreset("glm-5.2", "GLM-5.2（745B MoE 旗舰）",
                        max_tokens=8192, context_window=131072),
            # GLM-4.x 系列
            ModelPreset("glm-4.6", "GLM-4.6（Agentic Coding 增强）",
                        max_tokens=8192, context_window=131072),
            ModelPreset("glm-4.5", "GLM-4.5（开源智能体）",
                        max_tokens=8192, context_window=131072),
            ModelPreset("glm-4.5-flash", "GLM-4.5-Flash（免费）",
                        max_tokens=8192, context_window=131072),
            ModelPreset("glm-4.6v-flash", "GLM-4.6V-Flash（视觉，免费）",
                        max_tokens=8192, context_window=131072),
            # GLM-4 经典系列
            ModelPreset("glm-4-plus", "GLM-4-Plus（经典旗舰）",
                        max_tokens=4096, context_window=131072),
            ModelPreset("glm-4-air", "GLM-4-Air（轻量，高性价比）",
                        max_tokens=4096, context_window=131072),
            ModelPreset("glm-4-flash", "GLM-4-Flash（免费）",
                        max_tokens=4096, context_window=131072),
            ModelPreset("glm-4-long", "GLM-4-Long（长文本）",
                        max_tokens=4096, context_window=1000000),
        ],
    ),
    # ============================================================
    # 百川智能（Baichuan）
    # 文档: https://platform.baichuan-ai.com/docs/api
    # Base URL: https://api.baichuan-ai.com/v1
    # 注: 通用模型列表（无 M3-Plus，该型号不存在）
    # ============================================================
    ProviderPreset(
        key="baichuan",
        display_name="百川智能（Baichuan）",
        api_base="https://api.baichuan-ai.com/v1",
        keyring_key="llm_api_key",
        key_apply_url="https://platform.baichuan-ai.com/console/apikey",
        doc_url="https://platform.baichuan-ai.com/docs/api",
        models=[
            ModelPreset("Baichuan4-Turbo", "Baichuan4-Turbo（通用旗舰）",
                        max_tokens=4096, context_window=32768),
            ModelPreset("Baichuan4-Air", "Baichuan4-Air（轻量）",
                        max_tokens=4096, context_window=32768),
            ModelPreset("Baichuan4", "Baichuan4（标准）",
                        max_tokens=4096, context_window=32768),
            ModelPreset("Baichuan3-Turbo", "Baichuan3-Turbo",
                        max_tokens=4096, context_window=8192),
            ModelPreset("Baichuan3-Turbo-128k", "Baichuan3-Turbo-128k（长上下文）",
                        max_tokens=4096, context_window=131072),
            ModelPreset("Baichuan2-Turbo", "Baichuan2-Turbo（经济）",
                        max_tokens=4096, context_window=8192),
        ],
    ),
    # ============================================================
    # MiniMax
    # 文档: https://platform.minimaxi.com/document/Models
    # Base URL: https://api.minimaxi.com/v1 （国内）
    # 模型命名: MiniMax-M3 / MiniMax-M2.7 等
    # ============================================================
    ProviderPreset(
        key="minimax",
        display_name="MiniMax",
        api_base="https://api.minimaxi.com/v1",
        keyring_key="llm_api_key",
        key_apply_url="https://platform.minimaxi.com/user-center/basic-information/interface-key",
        doc_url="https://platform.minimaxi.com/document/Models",
        models=[
            # M3 系列（2026.6 最新，Agent 推理）
            ModelPreset("MiniMax-M3", "MiniMax-M3（Agent 推理，长上下文）",
                        max_tokens=8192, context_window=262144),
            # M2.7 系列（2026.3）
            ModelPreset("MiniMax-M2.7", "MiniMax-M2.7",
                        max_tokens=8192, context_window=262144),
            ModelPreset("MiniMax-M2.7-highspeed", "MiniMax-M2.7-highspeed（高速版）",
                        max_tokens=8192, context_window=262144),
            # M2.5 系列（2026.2）
            ModelPreset("MiniMax-M2.5", "MiniMax-M2.5",
                        max_tokens=8192, context_window=262144),
            ModelPreset("MiniMax-M2.5-highspeed", "MiniMax-M2.5-highspeed（高速版）",
                        max_tokens=8192, context_window=262144),
            # M2 系列（2025.10）
            ModelPreset("MiniMax-M2", "MiniMax-M2（编程 Agent）",
                        max_tokens=8192, context_window=262144),
            # 经典 abab 系列
            ModelPreset("abab6.5s-chat", "abab6.5s（快速响应）",
                        max_tokens=8192, context_window=245760),
            ModelPreset("abab6.5g-chat", "abab6.5g（高精度）",
                        max_tokens=8192, context_window=245760),
        ],
    ),
    # ============================================================
    # 零一万物（Yi）
    # 文档: https://platform.lingyiwanwu.com/docs
    # Base URL: https://api.lingyiwanwu.com/v1
    # ============================================================
    ProviderPreset(
        key="yi",
        display_name="零一万物（Yi）",
        api_base="https://api.lingyiwanwu.com/v1",
        keyring_key="llm_api_key",
        key_apply_url="https://platform.lingyiwanwu.com/apikeys",
        doc_url="https://platform.lingyiwanwu.com/docs",
        models=[
            ModelPreset("yi-lightning", "Yi-Lightning（旗舰，LMSYS 世界第六）",
                        max_tokens=8192, context_window=131072),
            ModelPreset("yi-large", "Yi-Large（千亿参数）",
                        max_tokens=4096, context_window=32768),
            ModelPreset("yi-medium", "Yi-Medium（通用）",
                        max_tokens=4096, context_window=16384),
            ModelPreset("yi-light", "Yi-Light（轻量，快速）",
                        max_tokens=4096, context_window=16384),
            ModelPreset("yi-vision", "Yi-Vision（多模态）",
                        max_tokens=4096, context_window=16384),
            ModelPreset("yi-coder", "Yi-Coder（编程专用）",
                        max_tokens=4096, context_window=16384),
        ],
    ),
    # ============================================================
    # 科大讯飞（星火）
    # 文档: https://www.xfyun.cn/doc/spark/HTTP%E8%B0%83%E7%94%A8%E6%96%87%E6%A1%A3.html
    # Base URL: https://spark-api-open.xf-yun.com/v1 （OpenAI 兼容）
    # model 字段值（官方文档）: 4.0Ultra / generalv3.5 / max-32k / generalv3 / pro-128k / lite
    # 注: Max 版本 2026-03-10 下线，升级为 Ultra
    # ============================================================
    ProviderPreset(
        key="spark",
        display_name="科大讯飞（星火）",
        api_base="https://spark-api-open.xf-yun.com/v1",
        keyring_key="llm_api_key",
        key_apply_url="https://console.xfyun.cn/services/bm4",
        doc_url="https://www.xfyun.cn/doc/spark/HTTP%E8%B0%83%E7%94%A8%E6%96%87%E6%A1%A3.html",
        models=[
            ModelPreset("4.0Ultra", "星火 4.0 Ultra（非思考旗舰，32K）",
                        max_tokens=32768, context_window=32768),
            ModelPreset("generalv3.5", "星火 Max（generalv3.5）",
                        max_tokens=8192, context_window=8192),
            ModelPreset("max-32k", "星火 Max-32K",
                        max_tokens=32768, context_window=32768),
            ModelPreset("generalv3", "星火 Pro（generalv3）",
                        max_tokens=8192, context_window=8192),
            ModelPreset("pro-128k", "星火 Pro-128K（长上下文）",
                        max_tokens=32768, context_window=131072),
            ModelPreset("lite", "星火 Lite（免费）",
                        max_tokens=4096, context_window=8192),
        ],
    ),
]


def get_provider(key: str) -> ProviderPreset | None:
    """按键查找厂商"""
    for p in PROVIDERS:
        if p.key == key:
            return p
    return None


def list_provider_names() -> list[tuple[str, str]]:
    """返回 [(key, display_name), ...] 供下拉框使用"""
    return [(p.key, p.display_name) for p in PROVIDERS]
