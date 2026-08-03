"""模型配置服务 — 管理厂商/模型/Key/启用状态

存储格式（providers.yaml）：
    providers:
      - key: deepseek
        enabled: true
        models:
          - model_name: deepseek-v4-flash
            enabled: true
          - model_name: deepseek-chat
            enabled: false

API Key 按厂商独立存入 keyring（key 为 llm_api_key_<provider_key>），不明文落盘。
厂商预置信息（api_base、模型清单）从 presets/llm_providers.py 读取。

「已配置」= 厂商已填入 API Key；「已启用」= 厂商/模型的 enabled 开关为 true。
对话界面只能选择「已配置且已启用」的模型。
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Optional

import yaml

from presets.llm_providers import PROVIDERS, get_provider, ProviderPreset, ModelPreset
from utils.credentials import get_credential, set_credential, delete_credential

logger = logging.getLogger(__name__)

CONFIG_PATH = "providers.yaml"


def _keyring_key_for(provider_key: str) -> str:
    """厂商对应的 keyring key"""
    return f"llm_api_key_{provider_key}"


@dataclass
class ModelConfig:
    """单个模型的运行时配置"""
    model_name: str
    enabled: bool = True


@dataclass
class ProviderConfig:
    """单个厂商的运行时配置"""
    key: str
    api_key: str = ""          # 已解析的真实 Key（运行时填充，不落盘）
    enabled: bool = True
    models: list[ModelConfig] = field(default_factory=list)

    def get_enabled_models(self) -> list[str]:
        return [m.model_name for m in self.models if m.enabled]

    @property
    def configured(self) -> bool:
        """是否已配置（填入了 API Key）"""
        return bool(self.api_key)


class ModelConfigService:
    """模型配置服务 — 读写 providers.yaml + keyring"""

    def __init__(self, config_path: str = CONFIG_PATH):
        self.config_path = config_path
        self._cache: dict[str, ProviderConfig] = {}
        self.load()

    # ---------------------------------------------------------- 加载/保存
    def load(self):
        """从 providers.yaml 加载配置，缺失项用预置默认值补全"""
        data: dict[str, Any] = {}
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
            except Exception as e:
                logger.error(f"加载 {self.config_path} 失败: {e}")
                data = {}

        providers_data = data.get("providers", [])
        by_key = {p.get("key"): p for p in providers_data if p.get("key")}

        self._cache.clear()
        for preset in PROVIDERS:
            saved = by_key.get(preset.key, {})
            pc = ProviderConfig(
                key=preset.key,
                api_key="",  # 运行时从 keyring 填充
                enabled=saved.get("enabled", True),
            )
            saved_models = {m["model_name"]: m.get("enabled", True)
                            for m in saved.get("models", [])}
            for mp in preset.models:
                pc.models.append(ModelConfig(
                    model_name=mp.model_name,
                    enabled=saved_models.get(mp.model_name, True),
                ))
            self._cache[preset.key] = pc

        # 运行时填充 API Key（从 keyring，按厂商独立）
        for key, pc in self._cache.items():
            pc.api_key = get_credential(_keyring_key_for(key)) or ""

    def save(self):
        """保存配置到 providers.yaml（API Key 不落盘）"""
        providers_data = []
        for pc in self._cache.values():
            providers_data.append({
                "key": pc.key,
                "enabled": pc.enabled,
                "models": [{"model_name": m.model_name, "enabled": m.enabled}
                           for m in pc.models],
            })
        data = {"providers": providers_data}
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
        except Exception as e:
            logger.error(f"保存 {self.config_path} 失败: {e}")
            raise

    # ---------------------------------------------------------- 查询
    def list_providers(self) -> list[tuple[ProviderPreset, ProviderConfig]]:
        """返回 [(预置信息, 运行时配置), ...]"""
        result = []
        for preset in PROVIDERS:
            pc = self._cache.get(preset.key)
            if pc is None:
                continue
            result.append((preset, pc))
        return result

    def get_provider_config(self, key: str) -> ProviderConfig | None:
        return self._cache.get(key)

    def get_provider_preset(self, key: str) -> ProviderPreset | None:
        return get_provider(key)

    def list_enabled_models(self) -> list[tuple[str, str, str, str]]:
        """返回所有已配置(有Key)且已启用厂商下已启用的模型
        Returns: [(provider_key, provider_display_name, model_name, model_display_name), ...]
        """
        result = []
        for preset, pc in self.list_providers():
            if not pc.enabled or not pc.configured:
                continue
            model_display = {m.model_name: m.display_name for m in preset.models}
            for mc in pc.models:
                if mc.enabled:
                    result.append((
                        preset.key, preset.display_name,
                        mc.model_name, model_display.get(mc.model_name, mc.model_name)
                    ))
        return result

    def has_any_configured(self) -> bool:
        """是否至少有一个厂商已配置 API Key"""
        return any(pc.configured for pc in self._cache.values())

    # ---------------------------------------------------------- 修改
    def set_api_key(self, provider_key: str, value: str):
        """设置指定厂商的 API Key（存 keyring）"""
        if not value:
            raise ValueError("API Key 不能为空")
        set_credential(_keyring_key_for(provider_key), value)
        pc = self._cache.get(provider_key)
        if pc is not None:
            pc.api_key = value

    def get_api_key(self, provider_key: str) -> str:
        return get_credential(_keyring_key_for(provider_key)) or ""

    def clear_api_key(self, provider_key: str):
        delete_credential(_keyring_key_for(provider_key))
        pc = self._cache.get(provider_key)
        if pc is not None:
            pc.api_key = ""

    def set_provider_enabled(self, key: str, enabled: bool):
        if key in self._cache:
            self._cache[key].enabled = enabled
            self.save()

    def set_model_enabled(self, provider_key: str, model_name: str, enabled: bool):
        pc = self._cache.get(provider_key)
        if pc is None:
            return
        for mc in pc.models:
            if mc.model_name == model_name:
                mc.enabled = enabled
                break
        self.save()

    # ---------------------------------------------------------- 运行时
    def get_model_runtime(self, provider_key: str,
                          model_name: str) -> Optional[tuple[str, str, str]]:
        """获取指定模型的运行时配置 (api_base, api_key, model_name)
        仅当厂商已配置且模型已启用时返回。
        """
        preset = get_provider(provider_key)
        pc = self._cache.get(provider_key)
        if preset is None or pc is None:
            return None
        if not pc.configured or not pc.enabled:
            return None
        # 检查模型是否启用
        if not any(m.model_name == model_name and m.enabled for m in pc.models):
            return None
        return (preset.api_base, pc.api_key, model_name)

    def get_active_config(self) -> Optional[tuple[str, str, str]]:
        """获取默认使用的厂商配置 (api_base, model_name, api_key)
        优先返回第一个已配置且已启用厂商下的第一个已启用模型。
        """
        for preset, pc in self.list_providers():
            if not pc.enabled or not pc.configured:
                continue
            for mc in pc.models:
                if mc.enabled:
                    return (preset.api_base, mc.model_name, pc.api_key)
        return None

    def create_llm_client(self, provider_key: str, model_name: str):
        """为指定厂商+模型创建 LLM 客户端实例"""
        rt = self.get_model_runtime(provider_key, model_name)
        if rt is None:
            raise ValueError(
                f"模型 {provider_key}/{model_name} 未配置或未启用"
            )
        api_base, api_key, model = rt
        from adapters.openai_llm import OpenAILLMClient
        return OpenAILLMClient(
            api_base=api_base, api_key=api_key, model=model,
            temperature=0.3, max_tokens=4096, timeout=60,
        )

    def sync_default_to_config(self, config_path: str = "config.yaml"):
        """将第一个已配置且已启用的模型同步到 config.yaml 的 llm 段
        供应用启动时初始化 RAG 服务使用。
        """
        rt = self.get_active_config()
        if rt is None:
            return False
        api_base, model_name, _ = rt
        # 找到 provider_key 用于 keyring 占位符
        provider_key = None
        for preset, pc in self.list_providers():
            if pc.configured and pc.enabled:
                for mc in pc.models:
                    if mc.enabled and mc.model_name == model_name:
                        provider_key = preset.key
                        break
            if provider_key:
                break
        if provider_key is None:
            return False
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            cfg.setdefault("llm", {})
            cfg["llm"]["api_base"] = api_base
            cfg["llm"]["model"] = model_name
            cfg["llm"]["api_key"] = f"keyring:{_keyring_key_for(provider_key)}"
            # 清理旧的 api_key_env 字段（已废弃，改用 api_key）
            cfg["llm"].pop("api_key_env", None)
            with open(config_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)
            return True
        except Exception as e:
            logger.error(f"同步默认模型到 config.yaml 失败: {e}")
            return False
