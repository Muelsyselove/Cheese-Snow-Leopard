"""RRF 融合 + QdrantStore 混合检索单元测试

- rrf_fuse / rrf_fuse_with_scores: 纯算法，完整覆盖
- QdrantStore: 需真实服务，仅验证构造与契约（不连真实 Qdrant）
"""
from __future__ import annotations

import pytest

from models.chunk import Chunk
from services.rrf_fusion import rrf_fuse, rrf_fuse_with_scores


# ---------------------------------------------------------------------------
# 辅助构造
# ---------------------------------------------------------------------------
def _chunk(cid: int, content: str = "") -> Chunk:
    return Chunk(
        chunk_id=cid,
        content_hash="",
        doc_id=100,
        doc_name="test.md",
        content=content or f"chunk_{cid}",
        chunk_type="text",
    )


# ---------------------------------------------------------------------------
# RRF 融合核心算法
# ---------------------------------------------------------------------------
class TestRrfFuse:

    def test_empty_input(self):
        """空输入返回空列表"""
        assert rrf_fuse(k=60, limit=10) == []
        assert rrf_fuse([], [], k=60, limit=10) == []

    def test_single_list(self):
        """单路检索直接按原排名返回"""
        c1, c2, c3 = _chunk(1), _chunk(2), _chunk(3)
        result = rrf_fuse([(c1, 1), (c2, 2), (c3, 3)], k=60)
        assert result == [c1, c2, c3]

    def test_two_lists_consistent_ranking(self):
        """两路一致 → 一致命中的 chunk 排名提升"""
        c1, c2, c3 = _chunk(1), _chunk(2), _chunk(3)
        # 两路都把 c1 排第一 → c1 融合分数最高
        dense = [(c1, 1), (c2, 2), (c3, 3)]
        sparse = [(c1, 1), (c3, 2), (c2, 3)]
        result = rrf_fuse(dense, sparse, k=60)
        assert result[0] is c1  # 一致命中排第一

    def test_two_lists_disjoint(self):
        """两路完全不重叠 → 按 RRF 分数降序"""
        c1, c2, c3, c4 = _chunk(1), _chunk(2), _chunk(3), _chunk(4)
        dense = [(c1, 1), (c2, 2)]
        sparse = [(c3, 1), (c4, 2)]
        result = rrf_fuse(dense, sparse, k=60)
        # c1 和 c3 都是 rank=1，分数相同；c2 和 c4 都是 rank=2
        # 稳定排序按 chunk_id 升序 → c1, c3, c2, c4
        assert result[0] is c1
        assert result[1] is c3
        assert result[2] is c2
        assert result[3] is c4

    def test_multi_hit_accumulates_score(self):
        """多路命中的 chunk 分数累加，排名优于单路命中"""
        c1, c2 = _chunk(1), _chunk(2)
        # c1 在两路都排第 5，c2 在单路排第 1
        # c1 分数 = 2 * 1/(60+5) = 2/65 ≈ 0.0308
        # c2 分数 = 1/(60+1) = 1/61 ≈ 0.0164
        # c1 分数更高
        dense = [(c2, 1), (c1, 5)]
        sparse = [(c1, 5)]
        result = rrf_fuse(dense, sparse, k=60)
        assert result[0] is c1

    def test_limit_truncation(self):
        """limit 截断"""
        chunks = [_chunk(i) for i in range(10)]
        ranked = [(c, i + 1) for i, c in enumerate(chunks)]
        result = rrf_fuse(ranked, k=60, limit=3)
        assert len(result) == 3
        assert result == chunks[:3]

    def test_limit_zero(self):
        """limit=0 返回空"""
        c1 = _chunk(1)
        result = rrf_fuse([(c1, 1)], k=60, limit=0)
        assert result == []

    def test_invalid_k(self):
        """k 非正抛异常"""
        with pytest.raises(ValueError):
            rrf_fuse(k=0)
        with pytest.raises(ValueError):
            rrf_fuse(k=-1)

    def test_invalid_rank_skipped(self):
        """rank < 1 的条目被跳过"""
        c1, c2 = _chunk(1), _chunk(2)
        result = rrf_fuse([(c1, 0), (c2, 1)], k=60)
        assert result == [c2]

    def test_same_chunk_different_instances_merge(self):
        """同 chunk_id 的不同实例视为同一文档，分数累加"""
        # 两路返回同 chunk_id 的不同实例（元数据可能略有差异）
        c1a = _chunk(1, "dense view")
        c1b = _chunk(1, "sparse view")
        c2 = _chunk(2)
        result = rrf_fuse([(c1a, 1), (c2, 2)], [(c1b, 2)], k=60)
        # c1 在两路都命中，分数累加，排第一
        assert result[0].chunk_id == 1
        # 保留首个出现的实例
        assert result[0].content == "dense view"

    def test_score_decreases_with_rank(self):
        """排名越靠后分数越低"""
        chunks = [_chunk(i) for i in range(5)]
        ranked = [(c, i + 1) for i, c in enumerate(chunks)]
        scored = rrf_fuse_with_scores(ranked, k=60)
        # 分数严格递减
        for i in range(len(scored) - 1):
            assert scored[i][1] > scored[i + 1][1]
        # 第一个分数 = 1/(60+1)
        assert scored[0][1] == pytest.approx(1 / 61)

    def test_three_lists(self):
        """三路融合"""
        c1, c2, c3 = _chunk(1), _chunk(2), _chunk(3)
        dense = [(c1, 1), (c2, 3)]
        sparse = [(c2, 1), (c3, 2)]
        colbert = [(c1, 2), (c3, 1)]
        result = rrf_fuse(dense, sparse, colbert, k=60)
        # c1: 1/61 + 1/62, c2: 1/63 + 1/61, c3: 1/62 + 1/61
        # c1 和 c3 都有 rank=1 和 rank=2 的贡献，c2 有 rank=1 和 rank=3
        # c1 = 1/61 + 1/62 ≈ 0.0325
        # c3 = 1/62 + 1/61 ≈ 0.0325（同 c1）
        # c2 = 1/63 + 1/61 ≈ 0.0320
        # c1 和 c3 分数相同，按 id 升序 → c1 先
        assert result[0] is c1
        assert result[1] is c3
        assert result[2] is c2

    def test_k_affects_ranking(self):
        """k 值影响排名：k 小时排名靠前优势更大"""
        c1, c2 = _chunk(1), _chunk(2)
        # c1 两路 rank=3，c2 单路 rank=1
        dense = [(c2, 1), (c1, 3)]
        sparse = [(c1, 3)]
        # k=60: c1=2/63≈0.0317 > c2=1/61≈0.0164 → c1 第一
        assert rrf_fuse(dense, sparse, k=60)[0] is c1
        # k=1: c1=2/4=0.5 > c2=1/2=0.5 → 相同，按 id 升序 c1 第一
        # 但若 c1 单路 rank=5: c1=2/6=0.333 < c2=1/2=0.5 → c2 第一
        dense2 = [(c2, 1), (c1, 5)]
        sparse2 = [(c1, 5)]
        assert rrf_fuse(dense2, sparse2, k=1)[0] is c2


class TestRrfFuseWithScores:

    def test_returns_scores(self):
        """返回融合分数"""
        c1, c2 = _chunk(1), _chunk(2)
        scored = rrf_fuse_with_scores([(c1, 1), (c2, 2)], k=60)
        assert len(scored) == 2
        assert scored[0][0] is c1
        assert scored[0][1] == pytest.approx(1 / 61)
        assert scored[1][1] == pytest.approx(1 / 62)

    def test_multi_hit_score(self):
        """多路命中分数累加"""
        c1 = _chunk(1)
        scored = rrf_fuse_with_scores([(c1, 1)], [(c1, 1)], k=60)
        assert scored[0][1] == pytest.approx(2 / 61)

    def test_limit_truncation(self):
        """limit 截断"""
        chunks = [_chunk(i) for i in range(5)]
        ranked = [(c, i + 1) for i, c in enumerate(chunks)]
        scored = rrf_fuse_with_scores(ranked, k=60, limit=2)
        assert len(scored) == 2


# ---------------------------------------------------------------------------
# QdrantStore 构造与契约（不连真实 Qdrant）
# ---------------------------------------------------------------------------
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
        """客户端懒加载"""
        from adapters.qdrant_store import QdrantStore
        store = QdrantStore()
        assert store._client is None

    def test_vector_name_constants(self):
        """向量名约定常量"""
        from adapters.qdrant_store import QdrantStore
        assert QdrantStore.DENSE_NAME == "dense"
        assert QdrantStore.SPARSE_NAME == "sparse"

    def test_satisfies_protocol(self):
        """QdrantStore 满足 VectorStore Protocol"""
        from interfaces.vectorstore import VectorStore
        from adapters.qdrant_store import QdrantStore
        store = QdrantStore()
        for method in ("upsert", "search", "delete", "update_payload", "exists"):
            assert hasattr(store, method)
        # 新增单路检索方法
        assert hasattr(store, "search_dense")
        assert hasattr(store, "search_sparse")
        assert hasattr(store, "ensure_collection")
