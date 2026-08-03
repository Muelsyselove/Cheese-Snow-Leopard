"""配置加载与组件工厂

配置加载时调用 resolve_credential_placeholder 解析 keyring:xxx 占位符为真实凭据。
工厂根据配置动态创建组件实例，业务层仅接收接口。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import yaml

from utils.credentials import resolve_credential_placeholder


@dataclass
class AppConfig:
    llm: dict
    encoding: dict
    vlm: dict
    embedding: dict
    storage: dict
    chunking: dict
    retrieval: dict
    concurrency: dict
    ui: dict


def load_config(path: str = "config.yaml") -> AppConfig:
    """加载配置文件并解析 keyring 占位符"""
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    data = _resolve_credentials(data)
    return AppConfig(
        llm=data["llm"],
        encoding=data.get("encoding", {"worker_id": 1}),
        vlm=data["vlm"],
        embedding=data["embedding"],
        storage=data["storage"],
        chunking=data["chunking"],
        retrieval=data["retrieval"],
        concurrency=data.get("concurrency", {}),
        ui=data.get("ui", {})
    )


def _resolve_credentials(obj):
    """递归解析 dict/list 中的 keyring:xxx 占位符"""
    if isinstance(obj, dict):
        return {k: _resolve_credentials(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve_credentials(v) for v in obj]
    return resolve_credential_placeholder(obj)


class ComponentFactory:
    """根据配置动态创建组件实例，业务层仅接收接口"""

    def __init__(self, config: AppConfig):
        self.config = config

    def create_parser(self):
        """创建文档解析器（统一接口，原 create_vlm 合并于此）"""
        provider = self.config.vlm["provider"]
        if provider == "A":
            from adapters.paddleocr_vl import PaddleOCRVLModel
            return PaddleOCRVLModel(**self.config.vlm["paddleocr_vl"])
        elif provider == "B":
            from adapters.mineru_vlm import MinerUModel
            return MinerUModel(**self.config.vlm["mineru_vlm"])
        elif provider == "C":
            from adapters.minicpm_vlm import MiniCPMVModel
            return MiniCPMVModel(**self.config.vlm["minicpm_v"])
        else:
            raise ValueError(f"未知 VLM provider: {provider}")

    def create_embedder(self):
        """创建文本向量化器"""
        provider = self.config.embedding["provider"]
        if provider == "A":
            from adapters.bge_embedder import BgeM3Embedder
            return BgeM3Embedder(**self.config.embedding["bge_m3"])
        elif provider == "B":
            from adapters.qwen3_embedder import Qwen3Embedder
            return Qwen3Embedder(**self.config.embedding["qwen3"])
        else:
            raise ValueError(f"未知 Embedding provider: {provider}")

    def create_llm(self):
        """创建文字 LLM 客户端"""
        from adapters.openai_llm import OpenAILLMClient
        cfg = self.config.llm
        return OpenAILLMClient(
            api_base=cfg["api_base"],
            api_key=cfg["api_key"],
            model=cfg["model"],
            temperature=cfg.get("temperature", 0.3),
            max_tokens=cfg.get("max_tokens", 4096),
            timeout=cfg.get("timeout", 60)
        )

    def create_vector_store(self, sparse_support: bool):
        """创建向量存储"""
        from adapters.qdrant_store import QdrantStore
        cfg = self.config.storage["qdrant"]
        return QdrantStore(
            host=cfg["host"], port=cfg["port"],
            collection=cfg["collection"],
            sparse_support=sparse_support
        )

    def create_snowflake(self):
        """创建 Snowflake ID 生成器"""
        from services.encoding import SnowflakeGenerator
        return SnowflakeGenerator(worker_id=self.config.encoding.get("worker_id", 1))

    def create_chunker(self, token_counter=None):
        """创建文档分块器（结构感知分块）

        :param token_counter: 可选的 TokenCounter，默认使用 CharTokenCounter（无第三方依赖）
        """
        from services.chunker import StructureAwareChunker
        cfg = self.config.chunking
        return StructureAwareChunker(
            target_tokens=cfg.get("target_tokens", 300),
            overlap_ratio=cfg.get("overlap_ratio", 0.15),
            min_chunk_tokens=cfg.get("min_chunk_tokens", 50),
            token_counter=token_counter,
        )
