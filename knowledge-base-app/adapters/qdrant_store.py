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
    """Qdrant 向量存储实现

    两种运行模式：
    - 服务器模式：连接 host:port 的 Qdrant 服务（生产方案）
    - 本地嵌入模式：local_path 指定存储目录，QdrantClient(path=...)
      无需服务器，零配置开箱即用。注意本地模式不支持服务端 BM25
      文本推理（Qwen3 降级路径），BGE-M3 客户端 sparse 不受影响。
    """

    DENSE_NAME = "dense"
    SPARSE_NAME = "sparse"

    def __init__(self, host: str = "localhost", port: int = 6333,
                 collection: str = "text_chunks",
                 sparse_support: bool = False,
                 local_path: Optional[str] = None):
        self.host = host
        self.port = port
        self.collection = collection
        self.sparse_support = sparse_support
        self.local_path = local_path
        self._client = None
        self._dim: Optional[int] = None

    @property
    def is_local_mode(self) -> bool:
        return bool(self.local_path)

    def _get_client(self):
        if self._client is None:
            from qdrant_client import QdrantClient
            if self.local_path:
                import os
                os.makedirs(self.local_path, exist_ok=True)
                self._client = QdrantClient(path=self.local_path)
                logger.info(f"Qdrant 本地嵌入模式: {self.local_path}")
            else:
                self._client = QdrantClient(host=self.host, port=self.port)
        return self._client

    def ensure_collection(self, dim: int):
        """确保 collection 存在且其 schema 与当前 Embedding 配置匹配。

        若已存在但 schema 不匹配（例如曾以 sparse_support=False 创建，现改用
        BGE-M3 需要 sparse 向量），则重建该 collection，避免 upsert 报
        "Not existing vector name error: sparse" 而无法向量化。

        Args:
            dim: dense 向量维度（如 BGE-M3=1024, Qwen3-0.6B=1024）
        """
        from qdrant_client.models import Distance, VectorParams, SparseVectorParams
        client = self._get_client()

        # 检查 collection 是否已存在(get_collection 在不存在时抛 404,需先列表检查)
        existing_collections = [c.name for c in client.get_collections().collections]
        if self.collection in existing_collections:
            if self._schema_matches(dim):
                self._dim = dim
                return
            logger.warning(
                f"Qdrant collection {self.collection} 的 schema 与当前 Embedding "
                f"配置不匹配（期望 dim={dim}, sparse={self.sparse_support}），重建以匹配配置"
            )
            client.delete_collection(self.collection)

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

    def _schema_matches(self, dim: int) -> bool:
        """校验已存在 collection 的 schema 是否匹配当前配置（dense 维度 + sparse 开关）。"""
        client = self._get_client()
        try:
            info = client.get_collection(self.collection)
        except Exception:
            return False
        params = getattr(getattr(info, "config", None), "params", None)
        if params is None:
            return False
        vectors = getattr(params, "vectors", None)
        existing_dim = None
        if isinstance(vectors, dict):
            dense = vectors.get(self.DENSE_NAME)
            existing_dim = dense.size if dense is not None else None
        elif vectors is not None:
            existing_dim = getattr(vectors, "size", None)
        sparse_vectors = getattr(params, "sparse_vectors", None) or {}
        has_sparse = bool(sparse_vectors) and self.SPARSE_NAME in sparse_vectors
        return existing_dim == dim and has_sparse == self.sparse_support

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
                "category_paths": chunk.category_paths,
                "bbox": chunk.bbox,
            }
            vector = {self.DENSE_NAME: emb.dense}
            if self.sparse_support and emb.sparse:
                indices = sorted(emb.sparse.keys())
                vector[self.SPARSE_NAME] = SparseVector(
                    indices=indices,
                    values=[emb.sparse[i] for i in indices],
                )
            points.append(PointStruct(
                id=chunk.chunk_id,
                vector=vector,
                payload=payload
            ))
        client.upsert(collection_name=self.collection, points=points)

    def search_dense(self, query_vec: EmbeddingResult, top_k: int = 20,
                     filters: Optional[dict] = None) -> list[tuple[Chunk, int]]:
        """Dense 向量检索，返回 (chunk, rank) 列表，rank 从 1 开始"""
        client = self._get_client()
        qfilter = self._build_filter(filters) if filters else None
        results = client.query_points(
            collection_name=self.collection,
            query=query_vec.dense,
            using=self.DENSE_NAME,
            limit=top_k,
            query_filter=qfilter,
        ).points
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
            from qdrant_client.models import SparseVector
            indices = sorted(query_vec.sparse.keys())
            sparse_vec = SparseVector(
                indices=indices,
                values=[query_vec.sparse[i] for i in indices],
            )
            results = client.query_points(
                collection_name=self.collection,
                query=sparse_vec,
                using=self.SPARSE_NAME,
                limit=top_k,
                query_filter=qfilter,
            ).points
        else:
            query_text = getattr(query_vec, "query_text", None)
            if not query_text:
                logger.debug("sparse 检索跳过：无 query_text 且无 sparse 向量")
                return []
            try:
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

        dense_hits = self.search_dense(query_vec, top_k=top_k, filters=filters)
        sparse_hits = []
        if self.sparse_support:
            sparse_hits = self.search_sparse(query_vec, top_k=top_k, filters=filters)

        if not sparse_hits:
            return [c for c, _ in dense_hits[:top_k]]

        fused = rrf_fuse(dense_hits, sparse_hits, k=60, limit=top_k)
        return fused

    def delete(self, chunk_ids: list[str]) -> None:
        """按 chunk_id（字符串形式）批量删除向量"""
        client = self._get_client()
        int_ids = [Chunk.parse_chunk_id_str(cid) for cid in chunk_ids]
        client.delete(collection_name=self.collection, points_selector=int_ids)

    def drop_collection(self) -> None:
        """删除整个 collection（知识库全量重置用）。

        异常时仅告警不抛出；无论成功与否都将缓存的维度信息置空，
        下次写入前由 ensure_collection 重建。
        """
        try:
            client = self._get_client()
            client.delete_collection(self.collection)
            logger.info(f"Qdrant collection 已删除: {self.collection}")
        except Exception as e:
            logger.warning(f"Qdrant collection 删除失败（忽略）: {e}")
        self._dim = None

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
            content_hash="",
            doc_id=p.get("doc_id", 0),
            doc_name=p.get("doc_name", ""),
            content=p.get("content", ""),
            chunk_type=p.get("chunk_type", "text"),
            page_number=p.get("page_number"),
            bbox=p.get("bbox"),
            categories=p.get("categories", []),
            category_paths=p.get("category_paths", []),
            vector_id=str(point.id)
        )
