"""RRF（Reciproical Rank Fusion）倒数排名融合 — 自研核心逻辑。

技术文档 6.2 混合检索三级管道的融合层：
- Dense 检索 → cosine top N
- Sparse 检索 → BM25 top N
- RRF 融合 → 候选集 top M

RRF 公式（基于排名，不依赖向量值，故 dense/sparse 分属不同向量空间不影响正确性）：
    score(d) = Σ_i  1 / (k + rank_i(d))

其中：
- rank_i(d) 为文档 d 在第 i 路检索结果中的排名（从 1 开始；未出现则该路不贡献）
- k 为平滑常数（config.retrieval.rrf_k，默认 60），抑制排名靠前的高权重

特性：
- 同一 chunk 在多路命中时分数累加（多路一致 → 排名提升）
- 仅在某路命中而另一路未命中时，单路贡献 1/(k+rank)
- 输入为 [(chunk, rank), ...]，输出为按融合分数降序的 chunk 列表
"""
from __future__ import annotations

from typing import Iterable

from models.chunk import Chunk


def rrf_fuse(*ranked_lists: list[tuple[Chunk, int]],
             k: int = 60, limit: int = 50) -> list[Chunk]:
    """RRF 倒数排名融合

    Args:
        *ranked_lists: 多路检索结果，每路为 [(chunk, rank), ...]，rank 从 1 开始
        k: 平滑常数（默认 60，技术文档 config.retrieval.rrf_k）
        limit: 返回的 Top-K 数量（默认 50）

    Returns:
        按 RRF 融合分数降序排列的 Chunk 列表（截断至 limit）

    Note:
        - chunk_id 相同的 chunk 视为同一文档，分数累加
        - 仅取首个出现的 chunk 实例（多路返回的同一 chunk 元数据一致）
        - rank 越小（排名越靠前）贡献越大
    """
    if k <= 0:
        raise ValueError(f"k 必须为正数，实际: {k}")
    if limit <= 0:
        return []

    scores: dict[int, float] = {}
    chunks: dict[int, Chunk] = {}

    for ranked in ranked_lists:
        for chunk, rank in ranked:
            if rank < 1:
                continue
            cid = chunk.chunk_id
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
            if cid not in chunks:
                chunks[cid] = chunk

    sorted_ids = sorted(scores.keys(), key=lambda cid: (-scores[cid], cid))
    return [chunks[cid] for cid in sorted_ids[:limit]]


def rrf_fuse_with_scores(*ranked_lists: list[tuple[Chunk, int]],
                         k: int = 60, limit: int = 50
                         ) -> list[tuple[Chunk, float]]:
    """RRF 融合，额外返回融合分数（调试/重排用）

    Returns:
        [(chunk, score), ...] 按分数降序
    """
    if k <= 0:
        raise ValueError(f"k 必须为正数，实际: {k}")
    if limit <= 0:
        return []

    scores: dict[int, float] = {}
    chunks: dict[int, Chunk] = {}

    for ranked in ranked_lists:
        for chunk, rank in ranked:
            if rank < 1:
                continue
            cid = chunk.chunk_id
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
            if cid not in chunks:
                chunks[cid] = chunk

    sorted_ids = sorted(scores.keys(), key=lambda cid: (-scores[cid], cid))
    return [(chunks[cid], scores[cid]) for cid in sorted_ids[:limit]]
