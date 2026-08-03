"""Qdrant 向量存储实现

稀疏向量来源约定：
- BGE-M3 模式：客户端计算 sparse 后上传，与 dense 同源
- Qwen3 模式：模型仅输出 dense，sparse 降级为 Qdrant 服务端 qdrant/bm25 转换
"""
from __future__ import annotations

from typing import Optional

from interfaces.vectorstore import VectorStore
from interfaces.embedder import EmbeddingResult
from models.chunk import Chunk


class QdrantStore:
    """Qdrant 向量存储实现"""

    def __init__(self, host: str = "localhost", port: int = 6333,
                 collection: str = "text_chunks",
                 sparse_support: bool = False):
        self.host = host
        self.port = port
        self.collection = collection
        self.sparse_support = sparse_support  # 是否启用稀疏向量（取决于 Embedder）
        self._client = None

    def _get_client(self):
        if self._client is None:
            from qdrant_client import QdrantClient
            self._client = QdrantClient(host=self.host, port=self.port)
        return self._client

    def ensure_collection(self, dim: int):
        """确保 collection 存在，按维度创建"""
        from qdrant_client.models import Distance, VectorParams, SparseVectorParams
        client = self._get_client()
        # TODO: 检查 collection 是否存在，按 dense(±sparse) 维度创建
        pass

    def upsert(self, chunks: list[Chunk],
               embeddings: list[EmbeddingResult]) -> None:
        """批量写入向量与元数据"""
        from qdrant_client.models import PointStruct
        client = self._get_client()
        points = []
        for chunk, emb in zip(chunks, embeddings):
            payload = {
                "chunk_id": chunk.chunk_id_str,
                "doc_id": chunk.doc_id,
                "doc_name": chunk.doc_name,
                "page_number": chunk.page_number,
                "chunk_type": chunk.chunk_type,
                "content": chunk.content,
                "categories": chunk.categories,
                "bbox": chunk.bbox,
            }
            vector = {"dense": emb.dense}
            if self.sparse_support and emb.sparse:
                vector["sparse"] = emb.sparse
            points.append(PointStruct(
                id=chunk.chunk_id,  # Qdrant 支持 int id
                vector=vector,
                payload=payload
            ))
        client.upsert(collection_name=self.collection, points=points)

    def search(self, query_vec: EmbeddingResult, top_k: int = 20,
               filters: Optional[dict] = None) -> list[Chunk]:
        """向量检索，返回 Top-K 块"""
        from qdrant_client.models import SearchRequest, Filter, FieldCondition, MatchValue
        client = self._get_client()
        # TODO: 实现 dense + sparse 混合检索 + RRF 融合
        results = client.search(
            collection_name=self.collection,
            query_vector=query_vec.dense,
            limit=top_k,
            query_filter=self._build_filter(filters) if filters else None
        )
        return [self._to_chunk(r) for r in results]

    def delete(self, chunk_ids: list[str]) -> None:
        """按 chunk_id（字符串形式）批量删除向量"""
        client = self._get_client()
        int_ids = [Chunk.parse_chunk_id_str(cid) for cid in chunk_ids]
        client.delete(collection_name=self.collection, points_selector=int_ids)

    def update_payload(self, chunk_id: str, payload: dict) -> None:
        """更新单个 chunk 的 payload（如分类变更）"""
        client = self._get_client()
        client.set_payload(
            collection_name=self.collection,
            payload=payload,
            points=[Chunk.parse_chunk_id_str(chunk_id)]
        )

    def exists(self, chunk_id: str) -> bool:
        """检查 chunk_id 是否存在"""
        client = self._get_client()
        result = client.retrieve(
            collection_name=self.collection,
            ids=[Chunk.parse_chunk_id_str(chunk_id)]
        )
        return len(result) > 0

    def _build_filter(self, filters: dict):
        """构建 Qdrant Filter"""
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        conditions = []
        for k, v in filters.items():
            conditions.append(FieldCondition(key=k, match=MatchValue(value=v)))
        return Filter(must=conditions)

    def _to_chunk(self, point) -> Chunk:
        """Qdrant 命中点转 Chunk"""
        p = point.payload
        return Chunk(
            chunk_id=point.id,
            content_hash="",  # payload 未存
            doc_id=p.get("doc_id", 0),
            doc_name=p.get("doc_name", ""),
            content=p.get("content", ""),
            chunk_type=p.get("chunk_type", "text"),
            page_number=p.get("page_number"),
            bbox=p.get("bbox"),
            categories=p.get("categories", []),
            vector_id=str(point.id)
        )
