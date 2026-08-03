"""溯源服务单元测试 — 系统级溯源核心保障"""
from __future__ import annotations

import pytest
from unittest.mock import patch

from services.trace_service import trace_references, trace_references_fallback
from utils.exceptions import TraceError


class TestTraceService:

    def test_normal_citation(self):
        """正常引用：AI 标注的 chunk_id 在检索结果集内"""
        answer = ("知识库采用 Agentic RAG【chunk_1751234567890】，"
                  "Qdrant 支持元数据过滤【chunk_1751234567891】")
        retrieved = {"chunk_1751234567890", "chunk_1751234567891", "chunk_1751234567892"}
        with patch("services.trace_service._query_chunk") as mock_q:
            from models.chunk import Chunk
            mock_q.side_effect = [
                Chunk(chunk_id=1751234567890, content_hash="h1", doc_id=1,
                      doc_name="doc1.pdf", content="内容1", chunk_type="text",
                      page_number=1, bbox=[0, 0, 100, 100]),
                Chunk(chunk_id=1751234567891, content_hash="h2", doc_id=1,
                      doc_name="doc1.pdf", content="内容2", chunk_type="text",
                      page_number=2, bbox=[0, 0, 100, 100]),
            ]
            refs = trace_references(answer, retrieved)
        assert len(refs) == 2
        assert {r["chunk_id"] for r in refs} == {"chunk_1751234567890", "chunk_1751234567891"}

    def test_hallucination_filtering(self):
        """幻觉过滤：AI 编造的 chunk_id 不在检索结果集内，应被过滤"""
        answer = "某知识来自【chunk_9999999999999]"  # 不在检索结果中
        retrieved = {"chunk_1751234567890", "chunk_1751234567891"}
        refs = trace_references(answer, retrieved)
        assert len(refs) == 0  # 幻觉 ID 被过滤，无需查 DB

    def test_no_citation_fallback(self):
        """回退机制：AI 未标注任何引用时，使用 retrieved_chunks 作为引用来源"""
        answer = "知识库采用 Agentic RAG 架构"  # 无引用标记
        retrieved = {"chunk_1751234567890", "chunk_1751234567891"}
        with patch("services.trace_service._query_chunk") as mock_q:
            from models.chunk import Chunk
            mock_q.side_effect = [
                Chunk(chunk_id=1751234567890, content_hash="h1", doc_id=1,
                      doc_name="doc1.pdf", content="内容1"),
                Chunk(chunk_id=1751234567891, content_hash="h2", doc_id=1,
                      doc_name="doc1.pdf", content="内容2"),
            ]
            refs = trace_references_fallback(answer, retrieved)
        assert len(refs) == 2

    def test_mixed_citation(self):
        """混合场景：部分引用有效，部分为幻觉"""
        answer = "来自【chunk_1751234567890】和【chunk_9999999999999】"
        retrieved = {"chunk_1751234567890", "chunk_1751234567891"}
        with patch("services.trace_service._query_chunk") as mock_q:
            from models.chunk import Chunk
            mock_q.return_value = Chunk(
                chunk_id=1751234567890, content_hash="h1", doc_id=1,
                doc_name="doc1.pdf", content="内容1"
            )
            refs = trace_references(answer, retrieved)
        assert len(refs) == 1
        assert refs[0]["chunk_id"] == "chunk_1751234567890"

    def test_trace_error_on_db_failure(self):
        """DB 查询失败时抛出 TraceError"""
        answer = "引用【chunk_1751234567890】"
        retrieved = {"chunk_1751234567890"}
        with patch("services.trace_service._query_chunk",
                   side_effect=RuntimeError("conn lost")):
            with pytest.raises(TraceError):
                trace_references(answer, retrieved)
