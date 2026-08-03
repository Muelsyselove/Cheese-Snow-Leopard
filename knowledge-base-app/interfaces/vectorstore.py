"""向量存储接口 — Qdrant/Milvus 均可实现"""
from __future__ import annotations

from typing import Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from models.chunk import Chunk
    from interfaces.embedder import EmbeddingResult


class VectorStore(Protocol):
    """向量存储接口"""

    def upsert(self, chunks: list["Chunk"],
               embeddings: list["EmbeddingResult"]) -> None:
        """批量写入向量与元数据"""
        ...

    def search(self, query_vec: "EmbeddingResult", top_k: int,
               filters: dict | None = None) -> list["Chunk"]:
        """向量检索，返回 Top-K 块"""
        ...

    def delete(self, chunk_ids: list[str]) -> None:
        """按 chunk_id（字符串形式）批量删除向量"""
        ...

    def update_payload(self, chunk_id: str, payload: dict) -> None:
        """更新单个 chunk 的 payload（如分类变更）"""
        ...

    def exists(self, chunk_id: str) -> bool:
        """检查 chunk_id 是否存在"""
        ...
