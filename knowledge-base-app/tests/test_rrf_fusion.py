"""RRF 融合 + QdrantStore 混合检索单元测试

- rrf_fuse / rrf_fuse_with_scores: 纯算法，完整覆盖
- QdrantStore: 需真实服务，仅验证构造与契约（不连真实 Qdrant）
"""
from __future__ import annotations

import pytest

from models.chunk import Chunk
from services.rrf_fusion import rrf_fuse, rrf_fuse_with_scores


def _chunk(cid: int, content: str = "") -> Chunk:
    return Chunk(
        chunk_id=cid,
        content_hash="",
        doc_id=100,
        doc_name="test.md",
        content=content or f"chunk_{cid}",
        chunk_type="text",
    )


class TestRrfFuse:

    def test_empty_input(self):
        assert rrf_fuse(k=60, limit=10) == []
        assert rrf_fuse([], [], k=60, limit=10) == []

    def test_single_list(self):
        c1, c2, c3 = _chunk(1), _chunk(2), _chunk(3)
        result = rrf_fuse([(c1, 1), (c2, 2), (c3, 3)], k=60)
        assert result == [c1, c2, c3]

    def test_two_lists_consistent_ranking(self):
        c1, c2, c3 = _chunk(1), _chunk(2), _chunk(3)
        dense = [(c1, 1), (c2, 2), (c3, 3)]
        sparse = [(c1, 1), (c3, 2), (c2, 3)]
        result = rrf_fuse(dense, sparse, k=60)
        assert result[0] is c1

    def test_two_lists_disjoint(self):
        c1, c2, c3, c4 = _chunk(1), _chunk(2), _chunk(3), _chunk(4)
        dense = [(c1, 1), (c2, 2)]
        sparse = [(c3, 1), (c4, 2)]
        result = rrf_fuse(dense, sparse, k=60)
        assert result[0] is c1
        assert result[1] is c3
        assert result[2] is c2
        assert result[3] is c4

    def test_multi_hit_accumulates_score(self):
        c1, c2 = _chunk(1), _chunk(2)
        dense = [(c2, 1), (c1, 5)]
        sparse = [(c1, 5)]
        result = rrf_fuse(dense, sparse, k=60)
        assert result[0] is c1

    def test_limit_truncation(self):
        chunks = [_chunk(i) for i in range(10)]
        ranked = [(c, i + 1) for i, c in enumerate(chunks)]
        result = rrf_fuse(ranked, k=60, limit=3)
        assert len(result) == 3
        assert result == chunks[:3]

    def test_limit_zero(self):
        c1 = _chunk(1)
        result = rrf_fuse([(c1, 1)], k=60, limit=0)
        assert result == []

    def test_invalid_k(self):
        with pytest.raises(ValueError):
            rrf_fuse(k=0)
        with pytest.raises(ValueError):
            rrf_fuse(k=-1)

    def test_invalid_rank_skipped(self):
        c1, c2 = _chunk(1), _chunk(2)
        result = rrf_fuse([(c1, 0), (c2, 1)], k=60)
        assert result == [c2]

    def test_same_chunk_different_instances_merge(self):
        c1a = _chunk(1, "dense view")
        c1b = _chunk(1, "sparse view")
        c2 = _chunk(2)
        result = rrf_fuse([(c1a, 1), (c2, 2)], [(c1b, 2)], k=60)
        assert result[0].chunk_id == 1
        assert result[0].content == "dense view"

    def test_score_decreases_with_rank(self):
        chunks = [_chunk(i) for i in range(5)]
        ranked = [(c, i + 1) for i, c in enumerate(chunks)]
        scored = rrf_fuse_with_scores(ranked, k=60)
        for i in range(len(scored) - 1):
            assert scored[i][1] > scored[i + 1][1]
        assert scored[0][1] == pytest.approx(1 / 61)

    def test_three_lists(self):
        c1, c2, c3 = _chunk(1), _chunk(2), _chunk(3)
        dense = [(c1, 1), (c2, 3)]
        sparse = [(c2, 1), (c3, 2)]
        colbert = [(c1, 2), (c3, 1)]
        result = rrf_fuse(dense, sparse, colbert, k=60)
        assert result[0] is c1
        assert result[1] is c3
        assert result[2] is c2

    def test_k_affects_ranking(self):
        c1, c2 = _chunk(1), _chunk(2)
        dense = [(c2, 1), (c1, 3)]
        sparse = [(c1, 3)]
        assert rrf_fuse(dense, sparse, k=60)[0] is c1
        dense2 = [(c2, 1), (c1, 5)]
        sparse2 = [(c1, 5)]
        assert rrf_fuse(dense2, sparse2, k=1)[0] is c2


class TestRrfFuseWithScores:

    def test_returns_scores(self):
        c1, c2 = _chunk(1), _chunk(2)
        scored = rrf_fuse_with_scores([(c1, 1), (c2, 2)], k=60)
        assert len(scored) == 2
        assert scored[0][0] is c1
        assert scored[0][1] == pytest.approx(1 / 61)
        assert scored[1][1] == pytest.approx(1 / 62)

    def test_multi_hit_score(self):
        c1 = _chunk(1)
        scored = rrf_fuse_with_scores([(c1, 1)], [(c1, 1)], k=60)
        assert scored[0][1] == pytest.approx(2 / 61)

    def test_limit_truncation(self):
        chunks = [_chunk(i) for i in range(5)]
        ranked = [(c, i + 1) for i, c in enumerate(chunks)]
        scored = rrf_fuse_with_scores(ranked, k=60, limit=2)
        assert len(scored) == 2


class TestQdrantStoreConfig:

    def test_construct_defaults(self):
        from adapters.qdrant_store import QdrantStore
        store = QdrantStore()
        assert store.host == "localhost"
        assert store.port == 6333
        assert store.collection == "text_chunks"
        assert store.sparse_support is False
        assert store._client is None
        assert store._dim is None

    def test_construct_with_sparse(self):
        from adapters.qdrant_store import QdrantStore
        store = QdrantStore(sparse_support=True)
        assert store.sparse_support is True

    def test_lazy_client(self):
        from adapters.qdrant_store import QdrantStore
        store = QdrantStore()
        assert store._client is None

    def test_vector_name_constants(self):
        from adapters.qdrant_store import QdrantStore
        assert QdrantStore.DENSE_NAME == "dense"
        assert QdrantStore.SPARSE_NAME == "sparse"

    def test_satisfies_protocol(self):
        from interfaces.vectorstore import VectorStore
        from adapters.qdrant_store import QdrantStore
        store = QdrantStore()
        for method in ("upsert", "search", "delete", "update_payload", "exists"):
            assert hasattr(store, method)
        assert hasattr(store, "search_dense")
        assert hasattr(store, "search_sparse")
        assert hasattr(store, "ensure_collection")
