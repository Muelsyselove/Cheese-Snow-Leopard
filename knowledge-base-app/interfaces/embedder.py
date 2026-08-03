"""文本向量化接口 — 文本块与图片块（描述文本）统一走此接口。

用户可选 BGE-M3 或 Qwen3-Embedding 实现。无独立图片 Embedder。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class EmbeddingResult:
    """向量化结果 — 支持三模态（dense/sparse/colbert）"""
    dense: list[float]                        # 稠密向量（必有）
    sparse: dict[str, float] = field(default_factory=dict)   # 稀疏向量（BGE-M3 客户端有，Qwen3 无）
    colbert: list[list[float]] = field(default_factory=list)  # 多向量（仅 BGE-M3 ColBERT 模式）


class Embedder(Protocol):
    """文本向量化接口 — 文本块与图片块（描述文本）统一走此接口。"""

    def encode(self, texts: list[str]) -> list[EmbeddingResult]:
        """批量编码文本，返回向量结果列表"""
        ...

    def encode_query(self, query: str) -> EmbeddingResult:
        """编码查询文本（Qwen3 模式会自动加 instruction 前缀）"""
        ...

    @property
    def supports_sparse(self) -> bool:
        """是否支持稀疏向量：BGE-M3=True, Qwen3=False"""
        ...

    @property
    def supports_colbert(self) -> bool:
        """是否支持 ColBERT 多向量：BGE-M3=True, Qwen3=False"""
        ...
