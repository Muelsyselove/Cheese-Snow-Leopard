"""Qdrant 向量存储实现

稀疏向量来源约定：
- BGE-M3 模式：客户端计算 sparse 后上传，与 dense 同源
- Qwen3 模式：模型仅输出 dense，sparse 降级为 Qdrant 服务端 qdrant/bm25 转换

混合检索（技术文档 6.2）：
- Dense 检索 → Qdrant cosine top N
- Sparse 检索 → Qdrant BM25 top N（客户端 sparse 或服务端 bm25）
- 两路结果由 rag_service 调用 services.rrf_fusion 做 RRF 融合
- 本类的 search 返回融合后的 Top-K；search_dense/search_sparse 返回单路结果
"""
from __future__ import annotations

import logging
from typing import Optional

from interfaces.vectorstore import VectorStore
from interfaces.embedder import EmbeddingResult
from models.chunk import Chunk

logger = logging.getLogger(__name__)


class QdrantStore:
    """Qdrant 向量存储实现"""

    # Qdrant 向量名约定
    DENSE_NAME = "dense"
    SPARSE_NAME = "sparse"

    def __init__(self, host: str = "localhost", port: int = 6333,
                 collection: str = "text_chunks",
                 sparse_support: bool = False):
        self.host = host
        self.port = port
        self.collection = collection
        self.sparse_support = sparse_support  # 是否启用稀疏向量（取决于 Embedder）
        self._client = None
        self._dim: Optional[int] = None  # 已创建 collection 的 dense 维度

    def _get_client(self):
        if self._client is None:
            from qdrant_client import QdrantClient
            self._client = QdrantClient(host=self.host, port=self.port)
        return self._client

    def ensure_collection(self, dim: int):
        """确保 collection 存在，按 dense(±sparse) 维度创建

        Args:
            dim: dense 向量维度（如 BGE-M3=1024, Qwen3-0.6B=1024）
        """
        from qdrant_client.models import Distance, VectorParams, SparseVectorParams
        client = self._get_client()

        # 已存在则跳过（维度不一致时重建由 rebuild_worker 负责）
        existing = client.get_collection(self.collection)
        if existing is not None:
            self._dim = dim
            return

        vectors_config = {self.DENSE_NAME: VectorParams(size=dim, distance=Distance.COSINE)}
        sparse_vectors_config = None
        if self.sparse_support:
            sparse_vectors_config = {self.SPARSE_NAME: SparseVectorParams()}

        client.create_collection(
            collection_name=self.collection,
            vectors_config=vectors_config,
            sparse_vectors_config=sparse_vectors_config,
        )
        self._dim = dim
        logger.info(f"Qdrant collection 已创建: {self.collection} (dim={dim}, sparse={self.sparse_support})")

    def upsert(self, chunks: list[Chunk],
               embeddings: list[EmbeddingResult]) -> None:
        """批量写入向量与元数据"""
        from qdrant_client.models import PointStruct, SparseVector
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
            vector = {self.DENSE_NAME: emb.dense}
            if self.sparse_support and emb.sparse:
                # Qdrant 要求 sparse 为 SparseVector(indices, values)
                indices = sorted(emb.sparse.keys())
                vector[self.SPARSE_NAME] = SparseVector(
                    indices=indices,
                    values=[emb.sparse[i] for i in indices],
                )
            points.append(PointStruct(
                id=chunk.chunk_id,  # Qdrant 支持 int id
                vector=vector,
                payload=payload
            ))
        client.upsert(collection_name=self.collection, points=points)

    # ------------------------------------------------------------------
    # 单路检索（供 rag_service 做 RRF 融合）
    # ------------------------------------------------------------------
    def search_dense(self, query_vec: EmbeddingResult, top_k: int = 20,
                     filters: Optional[dict] = None) -> list[tuple[Chunk, int]]:
        """Dense 向量检索，返回 (chunk, rank) 列表，rank 从 1 开始"""
        client = self._get_client()
        qfilter = self._build_filter(filters) if filters else None
        results = client.search(
            collection_name=self.collection,
            query_vector=(self.DENSE_NAME, query_vec.dense),
            limit=top_k,
            query_filter=qfilter,
        )
        return [(self._to_chunk(r), i + 1) for i, r in enumerate(results)]

    def search_sparse(self, query_vec: EmbeddingResult, top_k: int = 20,
                      filters: Optional[dict] = None) -> list[tuple[Chunk, int]]:
        """Sparse 检索，返回 (chunk, rank) 列表

        - BGE-M3 模式：用客户端计算的 query_vec.sparse 查询
        - Qwen3 模式：降级为 Qdrant 服务端 qdrant/bm25 文本检索
        """
        client = self._get_client()
        qfilter = self._build_filter(filters) if filters else None

        if self.sparse_support and query_vec.sparse:
            # 客户端 sparse 向量查询（BGE-M3 模式）
            from qdrant_client.models import SparseVector
            indices = sorted(query_vec.sparse.keys())
            sparse_vec = SparseVector(
                indices=indices,
                values=[query_vec.sparse[i] for i in indices],
            )
            results = client.search(
                collection_name=self.collection,
                query_vector=(self.SPARSE_NAME, sparse_vec),
                limit=top_k,
                query_filter=qfilter,
            )
        else:
            # 服务端 BM25 文本检索（Qwen3 降级模式）
            # query_vec 不含 sparse，用 query 文本走 qdrant/bm25
            # 此处 query_text 由调用方通过 query_vec 的附加字段或单独传入
            # 简化：若 query_vec 无 sparse 且无 query_text，返回空
            query_text = getattr(query_vec, "query_text", None)
            if not query_text:
                logger.debug("sparse 检索跳过：无 query_text 且无 sparse 向量")
                return []
            try:
                from qdrant_client.models import QueryResponse
                results = client.query_points(
                    collection_name=self.collection,
                    query=query_text,
                    using=self.SPARSE_NAME,
                    limit=top_k,
                    query_filter=qfilter,
                ).points
            except Exception as e:
                logger.warning(f"服务端 BM25 检索失败，降级为空结果: {e}")
                return []

        return [(self._to_chunk(r), i + 1) for i, r in enumerate(results)]

    def search(self, query_vec: EmbeddingResult, top_k: int = 20,
               filters: Optional[dict] = None) -> list[Chunk]:
        """混合检索 + RRF 融合，返回 Top-K 块

        内部调用 search_dense + search_sparse，通过 RRF 融合后取 final_top_k。
        """
        from services.rrf_fusion import rrf_fuse

        # 单路检索（各取 top_k，融合后截断）
        dense_hits = self.search_dense(query_vec, top_k=top_k, filters=filters)
        sparse_hits = []
        if self.sparse_support:
            sparse_hits = self.search_sparse(query_vec, top_k=top_k, filters=filters)

        if not sparse_hits:
            # 无 sparse 路时直接返回 dense 结果
            return [c for c, _ in dense_hits[:top_k]]

        # RRF 融合
        fused = rrf_fuse(dense_hits, sparse_hits, k=60, limit=top_k)
        return fused

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
